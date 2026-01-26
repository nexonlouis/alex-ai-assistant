// ============================================================================
// ALEX AI ASSISTANT - COMMON QUERIES REFERENCE
// Reusable Cypher queries for memory operations
// ============================================================================


// ============================================================================
// MEMORY STORAGE QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Store a new interaction
// Parameters: $id, $user_id, $user_message, $assistant_response, $intent,
//             $complexity_score, $model_used, $date
// ----------------------------------------------------------------------------

CREATE (i:Interaction {
  id: $id,
  user_id: $user_id,
  timestamp: datetime(),
  type: "chat",
  intent: $intent,
  user_message: $user_message,
  assistant_response: $assistant_response,
  complexity_score: $complexity_score,
  model_used: $model_used,
  token_count_input: size($user_message) / 4,
  token_count_output: size($assistant_response) / 4
})
WITH i
MATCH (u:User {id: $user_id})
MERGE (u)-[:HAD_INTERACTION]->(i)
WITH i
MATCH (d:Day {date: $date})
MERGE (i)-[:OCCURRED_ON]->(d)
RETURN i.id AS interaction_id;


// ----------------------------------------------------------------------------
// Store interaction with embedding
// Parameters: $id, $user_id, $user_message, $assistant_response, $embedding, $date
// ----------------------------------------------------------------------------

CREATE (i:Interaction {
  id: $id,
  user_id: $user_id,
  timestamp: datetime(),
  user_message: $user_message,
  assistant_response: $assistant_response,
  embedding: $embedding
})
WITH i
MATCH (d:Day {date: $date})
MERGE (i)-[:OCCURRED_ON]->(d)
RETURN i.id;


// ============================================================================
// MEMORY RETRIEVAL QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Get today's interactions
// Parameters: none (uses current date)
// ----------------------------------------------------------------------------

MATCH (d:Day {date: toString(date())})<-[:OCCURRED_ON]-(i:Interaction)
RETURN i.user_message, i.assistant_response, i.timestamp, i.intent
ORDER BY i.timestamp DESC;


// ----------------------------------------------------------------------------
// Get interactions for a specific date
// Parameters: $date
// ----------------------------------------------------------------------------

MATCH (d:Day {date: $date})<-[:OCCURRED_ON]-(i:Interaction)
OPTIONAL MATCH (ds:DailySummary)-[:SUMMARIZES]->(d)
RETURN d.date AS date,
       collect({
         id: i.id,
         user_message: i.user_message,
         assistant_response: i.assistant_response,
         timestamp: toString(i.timestamp),
         intent: i.intent
       }) AS interactions,
       ds.content AS daily_summary
ORDER BY i.timestamp;


// ----------------------------------------------------------------------------
// Get interactions for a date range
// Parameters: $start_date, $end_date
// ----------------------------------------------------------------------------

MATCH (d:Day)
WHERE d.date >= $start_date AND d.date <= $end_date
MATCH (d)<-[:OCCURRED_ON]-(i:Interaction)
RETURN d.date AS date, collect(i) AS interactions
ORDER BY d.date, i.timestamp;


// ----------------------------------------------------------------------------
// Get weekly context with daily summaries
// Parameters: $week_id (e.g., "2026-W04")
// ----------------------------------------------------------------------------

MATCH (w:Week {id: $week_id})
OPTIONAL MATCH (ws:WeeklySummary)-[:SUMMARIZES]->(w)
OPTIONAL MATCH (w)-[:CONTAINS_DAY]->(d:Day)
OPTIONAL MATCH (ds:DailySummary)-[:SUMMARIZES]->(d)
RETURN w.id AS week_id,
       w.week AS week_number,
       ws.content AS weekly_summary,
       collect(DISTINCT {
         date: d.date,
         day_name: d.day_name,
         summary: ds.content
       }) AS daily_summaries
ORDER BY d.date;


// ----------------------------------------------------------------------------
// Adaptive context retrieval (auto-select summary level)
// Parameters: $query_date
// ----------------------------------------------------------------------------

WITH date() AS today, date($query_date) AS queryDate,
     duration.inDays(date($query_date), date()).days AS daysAgo
CALL {
  WITH queryDate, daysAgo
  WHERE daysAgo <= 1
  MATCH (d:Day {date: toString(queryDate)})<-[:OCCURRED_ON]-(i:Interaction)
  RETURN "raw" AS level, collect(i.user_message + " -> " + left(i.assistant_response, 200)) AS content

  UNION ALL

  WITH queryDate, daysAgo
  WHERE daysAgo > 1 AND daysAgo <= 7
  MATCH (d:Day {date: toString(queryDate)})<-[:SUMMARIZES]-(ds:DailySummary)
  RETURN "daily" AS level, [ds.content] AS content

  UNION ALL

  WITH queryDate, daysAgo
  WHERE daysAgo > 7 AND daysAgo <= 30
  MATCH (d:Day {date: toString(queryDate)})
  MATCH (w:Week)-[:CONTAINS_DAY]->(d)
  MATCH (ws:WeeklySummary)-[:SUMMARIZES]->(w)
  RETURN "weekly" AS level, [ws.content] AS content

  UNION ALL

  WITH queryDate, daysAgo
  WHERE daysAgo > 30 AND daysAgo <= 365
  MATCH (m:Month {id: toString(queryDate.year) + "-" + toString(queryDate.month)})
  MATCH (ms:MonthlySummary)-[:SUMMARIZES]->(m)
  RETURN "monthly" AS level, [ms.content] AS content

  UNION ALL

  WITH queryDate, daysAgo
  WHERE daysAgo > 365
  MATCH (y:Year {year: queryDate.year})
  MATCH (ans:AnnualSummary)-[:SUMMARIZES]->(y)
  RETURN "annual" AS level, [ans.content] AS content
}
RETURN level, content, daysAgo;


// ============================================================================
// VECTOR SEARCH QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Semantic search on interactions
// Parameters: $embedding (1536-dim vector), $top_k, $min_score
// ----------------------------------------------------------------------------

CALL db.index.vector.queryNodes('vector_index_interaction', $top_k, $embedding)
YIELD node AS interaction, score
WHERE score >= $min_score
MATCH (interaction)-[:OCCURRED_ON]->(d:Day)
RETURN interaction.user_message,
       interaction.assistant_response,
       d.date AS date,
       score
ORDER BY score DESC;


// ----------------------------------------------------------------------------
// Semantic search across all summary levels
// Parameters: $embedding, $top_k, $min_score
// ----------------------------------------------------------------------------

CALL db.index.vector.queryNodes('vector_index_daily_summary', $top_k, $embedding)
YIELD node AS summary, score
WHERE score >= $min_score
MATCH (summary)-[:SUMMARIZES]->(d:Day)
RETURN "daily" AS level, summary.content, d.date AS period, score

UNION ALL

CALL db.index.vector.queryNodes('vector_index_weekly_summary', $top_k, $embedding)
YIELD node AS summary, score
WHERE score >= $min_score
MATCH (summary)-[:SUMMARIZES]->(w:Week)
RETURN "weekly" AS level, summary.content, w.id AS period, score

ORDER BY score DESC
LIMIT 10;


// ----------------------------------------------------------------------------
// Hybrid search: Vector entry + Graph traversal
// Parameters: $embedding, $min_score
// ----------------------------------------------------------------------------

CALL db.index.vector.queryNodes('vector_index_interaction', 5, $embedding)
YIELD node AS seed, score
WHERE score >= $min_score
// Get temporal context
MATCH (seed)-[:OCCURRED_ON]->(d:Day)
OPTIONAL MATCH (d)<-[:OCCURRED_ON]-(nearby:Interaction)
WHERE nearby <> seed
// Get topic context
OPTIONAL MATCH (seed)-[:DISCUSSES_TOPIC]->(t:Topic)<-[:DISCUSSES_TOPIC]-(topicRelated:Interaction)
WHERE topicRelated <> seed
// Get project context
OPTIONAL MATCH (seed)-[:RELATES_TO_PROJECT]->(p:Project)
RETURN seed.user_message AS query,
       seed.assistant_response AS response,
       score,
       d.date AS date,
       collect(DISTINCT nearby.user_message)[0..3] AS same_day_context,
       collect(DISTINCT topicRelated.user_message)[0..3] AS topic_related,
       p.name AS related_project;


// ============================================================================
// SUMMARIZATION QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Get interactions needing daily summarization
// ----------------------------------------------------------------------------

MATCH (d:Day)
WHERE d.date < toString(date())
  AND NOT EXISTS { MATCH (:DailySummary)-[:SUMMARIZES]->(d) }
  AND EXISTS { MATCH (d)<-[:OCCURRED_ON]-(:Interaction) }
RETURN d.date AS needs_summary
ORDER BY d.date
LIMIT 10;


// ----------------------------------------------------------------------------
// Get weeks needing summarization
// ----------------------------------------------------------------------------

MATCH (w:Week)
WHERE NOT EXISTS { MATCH (:WeeklySummary)-[:SUMMARIZES]->(w) }
  AND EXISTS { MATCH (w)-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(:DailySummary) }
WITH w
MATCH (w)-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(ds:DailySummary)
WITH w, count(ds) AS summary_count
WHERE summary_count >= 5  // At least 5 days summarized
RETURN w.id AS needs_summary, summary_count
ORDER BY w.id;


// ----------------------------------------------------------------------------
// Create daily summary
// Parameters: $date, $content, $key_topics, $interaction_count, $model_used
// ----------------------------------------------------------------------------

MATCH (d:Day {date: $date})
MERGE (ds:DailySummary {date: $date})
ON CREATE SET ds.generated_at = datetime(),
              ds.status = "completed"
SET ds.content = $content,
    ds.key_topics = $key_topics,
    ds.interaction_count = $interaction_count,
    ds.model_used = $model_used
MERGE (ds)-[:SUMMARIZES]->(d)
WITH ds, d
MATCH (d)<-[:OCCURRED_ON]-(i:Interaction)
MERGE (ds)-[:AGGREGATES]->(i)
RETURN ds.date, ds.status;


// ----------------------------------------------------------------------------
// Create weekly summary from daily summaries
// Parameters: $week_id, $content, $key_themes, $model_used
// ----------------------------------------------------------------------------

MATCH (w:Week {id: $week_id})
MATCH (w)-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(ds:DailySummary)
WITH w, collect(ds) AS dailySummaries
MERGE (ws:WeeklySummary {week_id: $week_id})
ON CREATE SET ws.generated_at = datetime(),
              ws.status = "completed",
              ws.year = w.year,
              ws.week_number = w.week
SET ws.content = $content,
    ws.key_themes = $key_themes,
    ws.days_covered = size(dailySummaries),
    ws.model_used = $model_used
MERGE (ws)-[:SUMMARIZES]->(w)
WITH ws, dailySummaries
UNWIND dailySummaries AS ds
MERGE (ws)-[:AGGREGATES]->(ds)
RETURN ws.week_id, ws.days_covered;


// ============================================================================
// SELF-KNOWLEDGE QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Store module analysis
// Parameters: $path, $name, $package, $docstring, $line_count, $dependencies, $exports
// ----------------------------------------------------------------------------

MERGE (mod:Module {path: $path})
SET mod.name = $name,
    mod.package = $package,
    mod.docstring = $docstring,
    mod.line_count = $line_count,
    mod.dependencies = $dependencies,
    mod.exports = $exports,
    mod.last_analyzed = datetime()
RETURN mod.path;


// ----------------------------------------------------------------------------
// Store class with methods
// Parameters: $fqn, $name, $module_path, $docstring, $methods (array of method objects)
// ----------------------------------------------------------------------------

MATCH (mod:Module {path: $module_path})
MERGE (cls:Class {fqn: $fqn})
SET cls.name = $name,
    cls.docstring = $docstring,
    cls.last_analyzed = datetime()
MERGE (mod)-[:CONTAINS_CLASS]->(cls)
WITH cls
UNWIND $methods AS method
MERGE (m:Method {id: $fqn + "." + method.name})
SET m.name = method.name,
    m.fqn = $fqn + "." + method.name,
    m.docstring = method.docstring,
    m.signature = method.signature,
    m.line_start = method.line_start,
    m.line_end = method.line_end
MERGE (cls)-[:HAS_METHOD]->(m)
RETURN cls.fqn, count(m) AS method_count;


// ----------------------------------------------------------------------------
// Search codebase by keyword
// Parameters: $query
// ----------------------------------------------------------------------------

CALL {
  MATCH (mod:Module)
  WHERE mod.name CONTAINS $query OR mod.docstring CONTAINS $query
  RETURN "module" AS type, mod.path AS path, mod.name AS name, mod.docstring AS description

  UNION ALL

  MATCH (cls:Class)
  WHERE cls.name CONTAINS $query OR cls.docstring CONTAINS $query
  RETURN "class" AS type, cls.fqn AS path, cls.name AS name, cls.docstring AS description

  UNION ALL

  MATCH (m:Method)
  WHERE m.name CONTAINS $query OR m.docstring CONTAINS $query
  RETURN "method" AS type, m.fqn AS path, m.name AS name, m.docstring AS description
}
RETURN type, path, name, description
LIMIT 20;


// ----------------------------------------------------------------------------
// Get module dependency graph
// ----------------------------------------------------------------------------

MATCH (mod:Module)-[:IMPORTS]->(dep:Module)
RETURN mod.name AS module, collect(dep.name) AS dependencies
ORDER BY mod.name;


// ----------------------------------------------------------------------------
// Find method call chains (up to 3 hops)
// Parameters: $method_name
// ----------------------------------------------------------------------------

MATCH path = (m1:Method)-[:CALLS*1..3]->(m2:Method)
WHERE m1.name = $method_name
RETURN [n IN nodes(path) | n.name] AS call_chain,
       length(path) AS depth;


// ============================================================================
// CONCEPT & ENTITY QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Link interaction to concepts (with extraction)
// Parameters: $interaction_id, $concepts (array of {name, confidence})
// ----------------------------------------------------------------------------

MATCH (i:Interaction {id: $interaction_id})
UNWIND $concepts AS concept
MERGE (c:Concept {name: concept.name})
ON CREATE SET c.normalized_name = toLower(replace(concept.name, " ", "_")),
              c.first_mentioned = datetime(),
              c.mention_count = 0
SET c.mention_count = c.mention_count + 1
MERGE (i)-[r:MENTIONS_CONCEPT]->(c)
SET r.confidence = concept.confidence,
    r.timestamp = datetime()
RETURN c.name, c.mention_count;


// ----------------------------------------------------------------------------
// Get trending concepts (last 7 days)
// ----------------------------------------------------------------------------

MATCH (d:Day)
WHERE d.date >= toString(date() - duration({days: 7}))
MATCH (d)<-[:OCCURRED_ON]-(i:Interaction)-[:MENTIONS_CONCEPT]->(c:Concept)
WITH c, count(DISTINCT i) AS recent_mentions
ORDER BY recent_mentions DESC
LIMIT 10
RETURN c.name, c.category, recent_mentions, c.mention_count AS total_mentions;


// ----------------------------------------------------------------------------
// Build concept network around a seed
// Parameters: $concept_name, $depth (1-3)
// ----------------------------------------------------------------------------

MATCH (seed:Concept {name: $concept_name})
CALL {
  WITH seed
  MATCH (seed)-[r:RELATED_TO]-(related:Concept)
  RETURN related, r.relationship_type AS rel_type, r.strength AS strength
}
RETURN seed.name AS center,
       seed.description,
       collect({
         concept: related.name,
         relationship: rel_type,
         strength: strength
       }) AS related_concepts;


// ----------------------------------------------------------------------------
// Link concepts as related
// Parameters: $concept1, $concept2, $relationship_type, $strength
// ----------------------------------------------------------------------------

MATCH (c1:Concept {name: $concept1})
MATCH (c2:Concept {name: $concept2})
MERGE (c1)-[r:RELATED_TO]->(c2)
SET r.relationship_type = $relationship_type,
    r.strength = $strength,
    r.discovered_at = datetime()
RETURN c1.name, c2.name, r.relationship_type;


// ============================================================================
// MAINTENANCE & HEALTH QUERIES
// ============================================================================

// ----------------------------------------------------------------------------
// Get database statistics
// ----------------------------------------------------------------------------

CALL {
  MATCH (n)
  WITH labels(n) AS nodeLabels, count(*) AS cnt
  UNWIND nodeLabels AS label
  RETURN label, sum(cnt) AS count
}
RETURN label AS node_type, count
ORDER BY count DESC;


// ----------------------------------------------------------------------------
// Get relationship statistics
// ----------------------------------------------------------------------------

MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(*) AS count
ORDER BY count DESC;


// ----------------------------------------------------------------------------
// Check time tree completeness for a year
// Parameters: $year
// ----------------------------------------------------------------------------

MATCH (y:Year {year: $year})-[:HAS_MONTH]->(m:Month)-[:HAS_DAY]->(d:Day)
RETURN m.month AS month, m.name AS month_name, count(d) AS days_created
ORDER BY m.month;


// ----------------------------------------------------------------------------
// Find orphaned nodes
// ----------------------------------------------------------------------------

// Orphaned interactions (not linked to any day)
MATCH (i:Interaction)
WHERE NOT EXISTS { MATCH (i)-[:OCCURRED_ON]->(:Day) }
RETURN "orphaned_interaction" AS issue, i.id AS id, i.timestamp AS created;

// Orphaned summaries
MATCH (ds:DailySummary)
WHERE NOT EXISTS { MATCH (ds)-[:SUMMARIZES]->(:Day) }
RETURN "orphaned_daily_summary" AS issue, ds.date AS id, ds.generated_at AS created;


// ----------------------------------------------------------------------------
// Update concept mention counts (maintenance task)
// ----------------------------------------------------------------------------

MATCH (c:Concept)
OPTIONAL MATCH (i:Interaction)-[:MENTIONS_CONCEPT]->(c)
WITH c, count(i) AS mentions
SET c.mention_count = mentions
RETURN c.name, c.mention_count;


// ============================================================================
// VERIFICATION QUERIES (Post-Schema Deployment)
// ============================================================================

// Check constraints exist
SHOW CONSTRAINTS;

// Check indexes exist
SHOW INDEXES;

// Verify time tree structure
MATCH (y:Year)-[:HAS_MONTH]->(m:Month)-[:HAS_DAY]->(d:Day)
WHERE y.year = 2026
RETURN y.year, count(DISTINCT m) AS months, count(DISTINCT d) AS days;

// Verify week linkages
MATCH (y:Year)-[:HAS_WEEK]->(w:Week)-[:CONTAINS_DAY]->(d:Day)
WHERE y.year = 2026
RETURN y.year, count(DISTINCT w) AS weeks, count(DISTINCT d) AS days_linked;

// Verify seed data
MATCH (u:User {id: "primary_user"}) RETURN u;
MATCH (c:Concept) RETURN count(c) AS concept_count;
MATCH (p:Project {id: "proj_alex_core"}) RETURN p.name, p.status;


// ============================================================================
// END OF QUERIES REFERENCE
// ============================================================================
