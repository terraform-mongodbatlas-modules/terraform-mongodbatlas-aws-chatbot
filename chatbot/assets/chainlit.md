# MongoDB for AI agents

Click **Upload documents** or the composer **Ingest** button, then try a starter question. After ingest, use the composer **Demo** button to show the questions again. **Cancel** returns to ordinary search.

Open **Chat Settings** (gear icon) to toggle **Keyword search**, **Vector search**, **LLM answer**, and **Rewrite follow-ups** per session. Turn **LLM answer** off to see ranked chunk hits without an LLM call. Keyword and vector toggles still run Atlas Search, Vector Search, or fused `$rankFusion` retrieval.

The chat remembers the earlier questions and answers of a session. With **Rewrite follow-ups** on, a follow-up such as "and what will it cost?" is restated as a standalone question before the search runs, and the **Searching for** step shows the text that was searched. The first message of a chat is always searched as typed.

Where the deployment enables it, a **Rerank results** switch reorders the retrieved chunks with Atlas native reranking (`$rerank`) before the answer. Turn it off and on with the same question to see what it changes: the retrieval step shows the ranked chunks and their scores either way.
