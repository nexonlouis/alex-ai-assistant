// ============================================================================
// ALEX AI ASSISTANT - TEMPORAL KNOWLEDGE GRAPH SCHEMA
// Neo4j Cypher Schema Definition
// Version: 1.0.0
// Date: 2026-01-25
// ============================================================================
//
// DEPLOYMENT INSTRUCTIONS:
// 1. Connect to your Neo4j AuraDB instance
// 2. Run this script in sections (constraints first, then indexes, then data)
// 3. Vector indexes require Neo4j 5.11+ or AuraDB
//
// ============================================================================

// ============================================================================
// SECTION 1: CONSTRAINTS (Run First)
// ============================================================================

// ----------------------------------------------------------------------------
// 1.1 TIME TREE CONSTRAINTS
// ----------------------------------------------------------------------------

CREATE CONSTRAINT constraint_year_unique IF NOT EXISTS
FOR (y:Year) REQUIRE y.year IS UNIQUE;

CREATE CONSTRAINT constraint_month_unique IF NOT EXISTS
FOR (m:Month) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT constraint_week_unique IF NOT EXISTS
FOR (w:Week) REQUIRE w.id IS UNIQUE;

CREATE CONSTRAINT constraint_day_unique IF NOT EXISTS
FOR (d:Day) REQUIRE d.date IS UNIQUE;

// ----------------------------------------------------------------------------
// 1.2 USER AND INTERACTION CONSTRAINTS
// ----------------------------------------------------------------------------

CREATE CONSTRAINT constraint_user_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT constraint_interaction_unique IF NOT EXISTS
FOR (i:Interaction) REQUIRE i.id IS UNIQUE;

CREATE CONSTRAINT constraint_conversation_unique IF NOT EXISTS
FOR (c:Conversation) REQUIRE c.id IS UNIQUE;

// ----------------------------------------------------------------------------
// 1.3 SUMMARY NODE CONSTRAINTS
// ----------------------------------------------------------------------------

CREATE CONSTRAINT constraint_daily_summary_unique IF NOT EXISTS
FOR (ds:DailySummary) REQUIRE ds.date IS UNIQUE;

CREATE CONSTRAINT constraint_weekly_summary_unique IF NOT EXISTS
FOR (ws:WeeklySummary) REQUIRE ws.week_id IS UNIQUE;

CREATE CONSTRAINT constraint_monthly_summary_unique IF NOT EXISTS
FOR (ms:MonthlySummary) REQUIRE ms.month_id IS UNIQUE;

CREATE CONSTRAINT constraint_annual_summary_unique IF NOT EXISTS
FOR (ans:AnnualSummary) REQUIRE ans.year IS UNIQUE;

// ----------------------------------------------------------------------------
// 1.4 SELF-KNOWLEDGE (CODE REPOSITORY) CONSTRAINTS
// ----------------------------------------------------------------------------

CREATE CONSTRAINT constraint_module_unique IF NOT EXISTS
FOR (mod:Module) REQUIRE mod.path IS UNIQUE;

CREATE CONSTRAINT constraint_class_unique IF NOT EXISTS
FOR (cls:Class) REQUIRE cls.fqn IS UNIQUE;

CREATE CONSTRAINT constraint_method_unique IF NOT EXISTS
FOR (m:Method) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT constraint_function_unique IF NOT EXISTS
FOR (f:Function) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT constraint_file_unique IF NOT EXISTS
FOR (file:File) REQUIRE file.path IS UNIQUE;

CREATE CONSTRAINT constraint_commit_unique IF NOT EXISTS
FOR (commit:Commit) REQUIRE commit.hash IS UNIQUE;

// ----------------------------------------------------------------------------
// 1.5 CONCEPT/ENTITY CONSTRAINTS
// ----------------------------------------------------------------------------

CREATE CONSTRAINT constraint_concept_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT constraint_topic_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.name IS UNIQUE;

CREATE CONSTRAINT constraint_project_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT constraint_person_unique IF NOT EXISTS
FOR (person:Person) REQUIRE person.id IS UNIQUE;

CREATE CONSTRAINT constraint_entity_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT constraint_tag_unique IF NOT EXISTS
FOR (tag:Tag) REQUIRE tag.name IS UNIQUE;


// ============================================================================
// SECTION 2: PERFORMANCE INDEXES
// ============================================================================

// ----------------------------------------------------------------------------
// 2.1 TIME TREE INDEXES
// ----------------------------------------------------------------------------

CREATE INDEX index_year_value IF NOT EXISTS
FOR (y:Year) ON (y.year);

CREATE INDEX index_month_number IF NOT EXISTS
FOR (m:Month) ON (m.month);

CREATE INDEX index_month_year IF NOT EXISTS
FOR (m:Month) ON (m.year);

CREATE INDEX index_week_number IF NOT EXISTS
FOR (w:Week) ON (w.week);

CREATE INDEX index_week_year IF NOT EXISTS
FOR (w:Week) ON (w.year);

CREATE INDEX index_day_dow IF NOT EXISTS
FOR (d:Day) ON (d.day_of_week);

CREATE INDEX index_day_year_month IF NOT EXISTS
FOR (d:Day) ON (d.year, d.month);

CREATE INDEX index_day_timestamp IF NOT EXISTS
FOR (d:Day) ON (d.timestamp);

// ----------------------------------------------------------------------------
// 2.2 INTERACTION INDEXES
// ----------------------------------------------------------------------------

CREATE INDEX index_interaction_timestamp IF NOT EXISTS
FOR (i:Interaction) ON (i.timestamp);

CREATE INDEX index_interaction_type IF NOT EXISTS
FOR (i:Interaction) ON (i.type);

CREATE INDEX index_interaction_intent IF NOT EXISTS
FOR (i:Interaction) ON (i.intent);

CREATE INDEX index_interaction_user_time IF NOT EXISTS
FOR (i:Interaction) ON (i.user_id, i.timestamp);

CREATE INDEX index_interaction_user IF NOT EXISTS
FOR (i:Interaction) ON (i.user_id);

CREATE INDEX index_conversation_timestamp IF NOT EXISTS
FOR (c:Conversation) ON (c.started_at);

CREATE INDEX index_conversation_status IF NOT EXISTS
FOR (c:Conversation) ON (c.status);

// ----------------------------------------------------------------------------
// 2.3 SUMMARY INDEXES
// ----------------------------------------------------------------------------

CREATE INDEX index_daily_summary_status IF NOT EXISTS
FOR (ds:DailySummary) ON (ds.status);

CREATE INDEX index_daily_summary_generated IF NOT EXISTS
FOR (ds:DailySummary) ON (ds.generated_at);

CREATE INDEX index_weekly_summary_status IF NOT EXISTS
FOR (ws:WeeklySummary) ON (ws.status);

CREATE INDEX index_monthly_summary_status IF NOT EXISTS
FOR (ms:MonthlySummary) ON (ms.status);

// ----------------------------------------------------------------------------
// 2.4 SELF-KNOWLEDGE INDEXES
// ----------------------------------------------------------------------------

CREATE INDEX index_module_name IF NOT EXISTS
FOR (mod:Module) ON (mod.name);

CREATE INDEX index_class_name IF NOT EXISTS
FOR (cls:Class) ON (cls.name);

CREATE INDEX index_method_name IF NOT EXISTS
FOR (m:Method) ON (m.name);

CREATE INDEX index_function_name IF NOT EXISTS
FOR (f:Function) ON (f.name);

CREATE INDEX index_file_extension IF NOT EXISTS
FOR (file:File) ON (file.extension);

CREATE INDEX index_commit_timestamp IF NOT EXISTS
FOR (commit:Commit) ON (commit.timestamp);

CREATE INDEX index_commit_ai_generated IF NOT EXISTS
FOR (commit:Commit) ON (commit.is_ai_generated);

// ----------------------------------------------------------------------------
// 2.5 CONCEPT/ENTITY INDEXES
// ----------------------------------------------------------------------------

CREATE INDEX index_concept_category IF NOT EXISTS
FOR (c:Concept) ON (c.category);

CREATE INDEX index_concept_mention_count IF NOT EXISTS
FOR (c:Concept) ON (c.mention_count);

CREATE INDEX index_topic_relevance IF NOT EXISTS
FOR (t:Topic) ON (t.relevance_score);

CREATE INDEX index_project_status IF NOT EXISTS
FOR (p:Project) ON (p.status);

CREATE INDEX index_person_type IF NOT EXISTS
FOR (person:Person) ON (person.type);

CREATE INDEX index_entity_type IF NOT EXISTS
FOR (e:Entity) ON (e.type);

CREATE INDEX index_tag_usage IF NOT EXISTS
FOR (tag:Tag) ON (tag.usage_count);


// ============================================================================
// SECTION 3: VECTOR INDEXES FOR HYBRID RETRIEVAL
// Requires Neo4j 5.11+ or AuraDB with vector support
// Dimension: 1536 (compatible with Gemini/OpenAI embeddings)
// ============================================================================

// ----------------------------------------------------------------------------
// 3.1 INTERACTION VECTOR INDEX
// ----------------------------------------------------------------------------

CREATE VECTOR INDEX vector_index_interaction IF NOT EXISTS
FOR (i:Interaction) ON (i.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// ----------------------------------------------------------------------------
// 3.2 SUMMARY VECTOR INDEXES
// ----------------------------------------------------------------------------

CREATE VECTOR INDEX vector_index_daily_summary IF NOT EXISTS
FOR (ds:DailySummary) ON (ds.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_weekly_summary IF NOT EXISTS
FOR (ws:WeeklySummary) ON (ws.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_monthly_summary IF NOT EXISTS
FOR (ms:MonthlySummary) ON (ms.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_annual_summary IF NOT EXISTS
FOR (ans:AnnualSummary) ON (ans.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// ----------------------------------------------------------------------------
// 3.3 CONCEPT/ENTITY VECTOR INDEXES
// ----------------------------------------------------------------------------

CREATE VECTOR INDEX vector_index_concept IF NOT EXISTS
FOR (c:Concept) ON (c.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_topic IF NOT EXISTS
FOR (t:Topic) ON (t.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_project IF NOT EXISTS
FOR (p:Project) ON (p.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// ----------------------------------------------------------------------------
// 3.4 SELF-KNOWLEDGE VECTOR INDEXES
// ----------------------------------------------------------------------------

CREATE VECTOR INDEX vector_index_module IF NOT EXISTS
FOR (mod:Module) ON (mod.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_class IF NOT EXISTS
FOR (cls:Class) ON (cls.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX vector_index_method IF NOT EXISTS
FOR (m:Method) ON (m.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};


// ============================================================================
// SECTION 4: FULLTEXT INDEXES
// ============================================================================

// Fulltext index on interaction content
CREATE FULLTEXT INDEX fulltext_interaction_content IF NOT EXISTS
FOR (i:Interaction) ON EACH [i.user_message, i.assistant_response];

// Fulltext index on summaries
CREATE FULLTEXT INDEX fulltext_daily_summary IF NOT EXISTS
FOR (ds:DailySummary) ON EACH [ds.content];

CREATE FULLTEXT INDEX fulltext_weekly_summary IF NOT EXISTS
FOR (ws:WeeklySummary) ON EACH [ws.content];

// Fulltext index on code documentation
CREATE FULLTEXT INDEX fulltext_module_docs IF NOT EXISTS
FOR (mod:Module) ON EACH [mod.docstring, mod.name];

CREATE FULLTEXT INDEX fulltext_class_docs IF NOT EXISTS
FOR (cls:Class) ON EACH [cls.docstring, cls.name];

CREATE FULLTEXT INDEX fulltext_method_docs IF NOT EXISTS
FOR (m:Method) ON EACH [m.docstring, m.name];

// Fulltext index on concepts
CREATE FULLTEXT INDEX fulltext_concepts IF NOT EXISTS
FOR (c:Concept) ON EACH [c.name, c.description];

CREATE FULLTEXT INDEX fulltext_topics IF NOT EXISTS
FOR (t:Topic) ON EACH [t.name, t.description];

CREATE FULLTEXT INDEX fulltext_projects IF NOT EXISTS
FOR (p:Project) ON EACH [p.name, p.description];


// ============================================================================
// SECTION 5: TIME TREE INITIALIZATION (2025-2026)
// ============================================================================

// ----------------------------------------------------------------------------
// 5.1 CREATE YEARS
// ----------------------------------------------------------------------------

MERGE (y2025:Year {year: 2025})
SET y2025.created_at = datetime(),
    y2025.label = "2025";

MERGE (y2026:Year {year: 2026})
SET y2026.created_at = datetime(),
    y2026.label = "2026";

// ----------------------------------------------------------------------------
// 5.2 CREATE MONTHS FOR 2025
// ----------------------------------------------------------------------------

UNWIND range(1, 12) AS monthNum
MERGE (m:Month {id: "2025-" + toString(monthNum)})
SET m.month = monthNum,
    m.year = 2025,
    m.name = CASE monthNum
      WHEN 1 THEN "January"
      WHEN 2 THEN "February"
      WHEN 3 THEN "March"
      WHEN 4 THEN "April"
      WHEN 5 THEN "May"
      WHEN 6 THEN "June"
      WHEN 7 THEN "July"
      WHEN 8 THEN "August"
      WHEN 9 THEN "September"
      WHEN 10 THEN "October"
      WHEN 11 THEN "November"
      WHEN 12 THEN "December"
    END,
    m.created_at = datetime()
WITH m
MATCH (y:Year {year: 2025})
MERGE (y)-[:HAS_MONTH]->(m);

// ----------------------------------------------------------------------------
// 5.3 CREATE MONTHS FOR 2026
// ----------------------------------------------------------------------------

UNWIND range(1, 12) AS monthNum
MERGE (m:Month {id: "2026-" + toString(monthNum)})
SET m.month = monthNum,
    m.year = 2026,
    m.name = CASE monthNum
      WHEN 1 THEN "January"
      WHEN 2 THEN "February"
      WHEN 3 THEN "March"
      WHEN 4 THEN "April"
      WHEN 5 THEN "May"
      WHEN 6 THEN "June"
      WHEN 7 THEN "July"
      WHEN 8 THEN "August"
      WHEN 9 THEN "September"
      WHEN 10 THEN "October"
      WHEN 11 THEN "November"
      WHEN 12 THEN "December"
    END,
    m.created_at = datetime()
WITH m
MATCH (y:Year {year: 2026})
MERGE (y)-[:HAS_MONTH]->(m);

// ----------------------------------------------------------------------------
// 5.4 CREATE WEEKS FOR 2025
// ----------------------------------------------------------------------------

UNWIND range(1, 52) AS weekNum
MERGE (w:Week {id: "2025-W" +
  CASE WHEN weekNum < 10 THEN "0" + toString(weekNum)
       ELSE toString(weekNum) END})
SET w.week = weekNum,
    w.year = 2025,
    w.created_at = datetime()
WITH w
MATCH (y:Year {year: 2025})
MERGE (y)-[:HAS_WEEK]->(w);

// ----------------------------------------------------------------------------
// 5.5 CREATE WEEKS FOR 2026
// ----------------------------------------------------------------------------

UNWIND range(1, 52) AS weekNum
MERGE (w:Week {id: "2026-W" +
  CASE WHEN weekNum < 10 THEN "0" + toString(weekNum)
       ELSE toString(weekNum) END})
SET w.week = weekNum,
    w.year = 2026,
    w.created_at = datetime()
WITH w
MATCH (y:Year {year: 2026})
MERGE (y)-[:HAS_WEEK]->(w);

// ----------------------------------------------------------------------------
// 5.6 CREATE DAYS FOR 2025 (Full Year)
// This may take a moment - creates 365 Day nodes
// ----------------------------------------------------------------------------

WITH date("2025-01-01") AS startDate, date("2025-12-31") AS endDate
WITH startDate, duration.inDays(startDate, endDate).days AS totalDays
UNWIND range(0, totalDays) AS dayOffset
WITH startDate + duration({days: dayOffset}) AS currentDate
MERGE (d:Day {date: toString(currentDate)})
SET d.year = currentDate.year,
    d.month = currentDate.month,
    d.day = currentDate.day,
    d.day_of_week = currentDate.dayOfWeek,
    d.day_name = CASE currentDate.dayOfWeek
      WHEN 1 THEN "Monday"
      WHEN 2 THEN "Tuesday"
      WHEN 3 THEN "Wednesday"
      WHEN 4 THEN "Thursday"
      WHEN 5 THEN "Friday"
      WHEN 6 THEN "Saturday"
      WHEN 7 THEN "Sunday"
    END,
    d.timestamp = datetime({year: currentDate.year, month: currentDate.month, day: currentDate.day}),
    d.week_number = currentDate.week,
    d.created_at = datetime()
WITH d, currentDate
MATCH (m:Month {id: toString(currentDate.year) + "-" + toString(currentDate.month)})
MERGE (m)-[:HAS_DAY]->(d)
WITH d, currentDate
MATCH (w:Week {id: toString(currentDate.year) + "-W" +
  CASE WHEN currentDate.week < 10 THEN "0" + toString(currentDate.week)
       ELSE toString(currentDate.week) END})
MERGE (w)-[:CONTAINS_DAY]->(d);

// ----------------------------------------------------------------------------
// 5.7 CREATE DAYS FOR 2026 (Full Year)
// ----------------------------------------------------------------------------

WITH date("2026-01-01") AS startDate, date("2026-12-31") AS endDate
WITH startDate, duration.inDays(startDate, endDate).days AS totalDays
UNWIND range(0, totalDays) AS dayOffset
WITH startDate + duration({days: dayOffset}) AS currentDate
MERGE (d:Day {date: toString(currentDate)})
SET d.year = currentDate.year,
    d.month = currentDate.month,
    d.day = currentDate.day,
    d.day_of_week = currentDate.dayOfWeek,
    d.day_name = CASE currentDate.dayOfWeek
      WHEN 1 THEN "Monday"
      WHEN 2 THEN "Tuesday"
      WHEN 3 THEN "Wednesday"
      WHEN 4 THEN "Thursday"
      WHEN 5 THEN "Friday"
      WHEN 6 THEN "Saturday"
      WHEN 7 THEN "Sunday"
    END,
    d.timestamp = datetime({year: currentDate.year, month: currentDate.month, day: currentDate.day}),
    d.week_number = currentDate.week,
    d.created_at = datetime()
WITH d, currentDate
MATCH (m:Month {id: toString(currentDate.year) + "-" + toString(currentDate.month)})
MERGE (m)-[:HAS_DAY]->(d)
WITH d, currentDate
MATCH (w:Week {id: toString(currentDate.year) + "-W" +
  CASE WHEN currentDate.week < 10 THEN "0" + toString(currentDate.week)
       ELSE toString(currentDate.week) END})
MERGE (w)-[:CONTAINS_DAY]->(d);


// ============================================================================
// SECTION 6: CREATE SEQUENTIAL DAY RELATIONSHIPS
// This enables efficient traversal between consecutive days
// ============================================================================

MATCH (d1:Day)
WHERE d1.year IN [2025, 2026]
WITH d1
ORDER BY d1.date
WITH collect(d1) AS days
UNWIND range(0, size(days)-2) AS i
WITH days[i] AS day1, days[i+1] AS day2
MERGE (day1)-[:NEXT_DAY]->(day2);


// ============================================================================
// SECTION 7: SEED DATA - PRIMARY USER
// ============================================================================

MERGE (u:User {id: "primary_user"})
SET u.name = "Primary User",
    u.created_at = datetime(),
    u.timezone = "UTC",
    u.preferences = {
      notification_enabled: true,
      summary_frequency: "daily",
      preferred_model: "gemini-3-flash-preview"
    },
    u.updated_at = datetime();


// ============================================================================
// SECTION 8: SEED DATA - INITIAL CONCEPTS
// Core concepts for Alex's self-understanding
// ============================================================================

// Technology concepts
UNWIND [
  {name: "knowledge_graph", category: "technology", description: "Graph-based data structure for representing knowledge"},
  {name: "neo4j", category: "technology", description: "Native graph database platform"},
  {name: "temporal_reasoning", category: "capability", description: "Ability to reason about time-based events and sequences"},
  {name: "recursive_summarization", category: "algorithm", description: "Hierarchical aggregation of information over time"},
  {name: "hybrid_retrieval", category: "algorithm", description: "Combining vector similarity with graph traversal"},
  {name: "langraph", category: "technology", description: "Framework for building stateful AI agents"},
  {name: "gemini", category: "technology", description: "Google's multimodal AI model family"},
  {name: "claude_code", category: "technology", description: "Anthropic's CLI tool for autonomous software engineering"},
  {name: "mcp_toolbox", category: "technology", description: "Model Context Protocol server for database access"},
  {name: "dual_cortex", category: "architecture", description: "Two-tier AI model architecture for cost-efficiency"}
] AS concept
MERGE (c:Concept {name: concept.name})
SET c.normalized_name = concept.name,
    c.category = concept.category,
    c.description = concept.description,
    c.first_mentioned = datetime(),
    c.mention_count = 0,
    c.relevance_score = 0.8;


// ============================================================================
// SECTION 9: SEED DATA - ALEX PROJECT
// ============================================================================

MERGE (p:Project {id: "proj_alex_core"})
SET p.name = "Alex AI Assistant",
    p.description = "Autonomous, self-reflective AI assistant with temporal knowledge graph memory",
    p.status = "in_progress",
    p.priority = "high",
    p.started_at = datetime(),
    p.milestones = [
      "Neo4j Schema Design",
      "MCP Toolbox Configuration",
      "LangGraph Agent Architecture",
      "Memory System Implementation",
      "Claude Code Integration",
      "GCP Deployment"
    ],
    p.current_milestone = "Neo4j Schema Design",
    p.tags = ["core", "infrastructure", "ai"]
WITH p
MATCH (d:Day {date: "2026-01-25"})
MERGE (p)-[:STARTED_ON]->(d);


// ============================================================================
// SECTION 10: RELATIONSHIP TYPE REFERENCE
// Documentation of all relationship types in the schema
// ============================================================================

/*
RELATIONSHIP TYPES SUMMARY:

TIME TREE RELATIONSHIPS:
- (Year)-[:HAS_MONTH]->(Month)
- (Year)-[:HAS_WEEK]->(Week)
- (Month)-[:HAS_DAY]->(Day)
- (Week)-[:CONTAINS_DAY]->(Day)
- (Day)-[:NEXT_DAY]->(Day)

USER/INTERACTION RELATIONSHIPS:
- (User)-[:HAD_INTERACTION]->(Interaction)
- (User)-[:PARTICIPATED_IN]->(Conversation)
- (Interaction)-[:OCCURRED_ON]->(Day)
- (Interaction)-[:PART_OF]->(Conversation)
- (Conversation)-[:STARTED_ON]->(Day)

SUMMARY RELATIONSHIPS:
- (DailySummary)-[:SUMMARIZES]->(Day)
- (DailySummary)-[:AGGREGATES]->(Interaction)
- (WeeklySummary)-[:SUMMARIZES]->(Week)
- (WeeklySummary)-[:AGGREGATES]->(DailySummary)
- (MonthlySummary)-[:SUMMARIZES]->(Month)
- (MonthlySummary)-[:AGGREGATES]->(WeeklySummary)
- (AnnualSummary)-[:SUMMARIZES]->(Year)
- (AnnualSummary)-[:AGGREGATES]->(MonthlySummary)

SELF-KNOWLEDGE RELATIONSHIPS:
- (File)-[:DEFINES]->(Module)
- (Module)-[:CONTAINS_CLASS]->(Class)
- (Module)-[:CONTAINS_FUNCTION]->(Function)
- (Class)-[:HAS_METHOD]->(Method)
- (Class)-[:INHERITS_FROM]->(Class)
- (Module)-[:IMPORTS]->(Module)
- (Method)-[:CALLS]->(Method)
- (Function)-[:CALLS]->(Function|Method)
- (Commit)-[:MODIFIED]->(File)
- (Commit)-[:COMMITTED_ON]->(Day)

CONCEPT/ENTITY RELATIONSHIPS:
- (Interaction)-[:MENTIONS_CONCEPT]->(Concept)
- (Interaction)-[:DISCUSSES_TOPIC]->(Topic)
- (Interaction)-[:RELATES_TO_PROJECT]->(Project)
- (Interaction)-[:MENTIONS_PERSON]->(Person)
- (Concept)-[:RELATED_TO]->(Concept)
- (Topic)-[:SUBTOPIC_OF]->(Topic)
- (Project)-[:STARTED_ON]->(Day)
- (Project)-[:COMPLETED_ON]->(Day)
- (Tag)-[:TAGS]->(Interaction|Project|Concept)
*/


// ============================================================================
// END OF SCHEMA DEFINITION
// ============================================================================
