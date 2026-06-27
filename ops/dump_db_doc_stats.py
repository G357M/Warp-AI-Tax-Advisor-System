import json
from sqlalchemy import text
from core.database import engine
engine.echo = False
q = text('''
SELECT d.source_url,
       COALESCE(length(d.full_text), 0) AS db_full_text_len,
       COUNT(c.id) AS chunk_count,
       COUNT(c.embedding) AS embedded_chunk_count
FROM documents d
LEFT JOIN document_chunks c ON c.document_id = d.id
GROUP BY d.id, d.source_url, d.full_text
ORDER BY d.source_url
''')
with engine.connect() as conn:
    for row in conn.execute(q).mappings():
        print(json.dumps(dict(row), ensure_ascii=False))
