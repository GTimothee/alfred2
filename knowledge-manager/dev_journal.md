## Development Journal: Entry 1

Date: September 28, 2025
Project: Knowledge Manager Engine
Status: Project Kickoff & Finalized Planning

This journal entry marks the official start of development. The architectural planning phase is complete. The goal is to document the core strategic decisions and assumptions before writing the first line of code.

The Vision (The "What")

To build a proactive, automated engine that discovers, ingests, and summarizes content from specified online sources, organizing it into a personal, searchable knowledge base for efficient learning and review.

Core Architectural Decisions (The "Why")

These are the foundational, "one-way door" decisions we have committed to:

    UI: Reflex.

        Why: To maintain development speed and stay within a single language (Python) ecosystem. This prioritizes building the engine over mastering complex frontend frameworks.

    Queue: AWS SQS.

        Why: To decouple the UI from the backend. This ensures the system is resilient and scalable; the UI can accept submissions even if the processing engine is busy or offline.

    Engine: Databricks.

        Why: To future-proof for large-scale, parallel data processing and long-running jobs. It is a strategic choice for the project's eventual needs, not its initial ones.

    Storage: AWS S3 + RDS.

        Why: To separate file storage (S3) from structured metadata (RDS). This provides data ownership, is cost-effective, and allows for efficient querying of job statuses and results.

    Deployment: AWS App Runner.

        Why: It is the simplest, most direct path to deploying a containerized web application without managing underlying server infrastructure.

Key Assumptions

The plan is based on the following assumptions, which may be revisited later:

    The free tier/API of Gemini is sufficient for initial summarization needs.

    The manual submission workflow is the highest priority; automated crawling is a "fast follow" feature.

    A daily or twice-daily crawl for new content is frequent enough.

    The primary user (me) is technical and values functionality over polished UI aesthetics for the MVP.

    The initial data volume is small, so hyper-optimization of cloud costs is not a day-one concern.