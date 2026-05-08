import asyncio

import import_data


class FakeService:
    def __init__(self):
        self.calls = []

    async def ingest_text(self, database_id, text, source="manual"):
        self.calls.append((database_id, text, source))
        return {"status": "success", "database": database_id}


def test_import_database_uses_raganything_service_ingest_text():
    service = FakeService()
    documents = [
        {
            "text": "商务彩铃迁移文本内容一，长度足够进入索引。",
            "metadata": {"source": "source-a.pdf", "chunk": 3},
        },
        {"text": "   "},
        {
            "text": "商务彩铃迁移文本内容二，长度足够进入索引。",
            "metadata": {"source": "source-b.docx"},
        },
    ]

    success, fail = asyncio.run(import_data.import_database(service, "商务彩铃", documents))

    assert success == 2
    assert fail == 0
    assert service.calls == [
        ("商务彩铃", "商务彩铃迁移文本内容一，长度足够进入索引。", "source-a.pdf#chunk-3"),
        ("商务彩铃", "商务彩铃迁移文本内容二，长度足够进入索引。", "source-b.docx#doc-3"),
    ]
