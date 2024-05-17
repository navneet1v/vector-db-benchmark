import multiprocessing as mp
import uuid
from typing import List

from opensearchpy import OpenSearch

from dataset_reader.base_reader import Record
from engine.base_client.upload import BaseUploader
from engine.clients.opensearch.config import (
    OPENSEARCH_INDEX,
    OPENSEARCH_INDEX_TIMEOUT,
    get_opensearch_client,
    _wait_for_es_status,
)


class ClosableOpenSearch(OpenSearch):
    def __del__(self):
        self.close()


class OpenSearchUploader(BaseUploader):
    client: OpenSearch = None
    upload_params = {}

    @classmethod
    def get_mp_start_method(cls):
        return "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"

    @classmethod
    def init_client(cls, host, distance, connection_params, upload_params):
        cls.client = get_opensearch_client(host, connection_params)
        cls.upload_params = upload_params

    @classmethod
    def upload_batch(cls, batch: List[Record]):
        operations = []
        for record in batch:
            vector_id = uuid.UUID(int=record.id).hex
            operations.append({"index": {"_id": vector_id}})
            operations.append({"vector": record.vector, **(record.metadata or {})})

        cls.client.bulk(
            index=OPENSEARCH_INDEX,
            body=operations,
            params={
                "timeout": OPENSEARCH_INDEX_TIMEOUT,
            },
        )

    @classmethod
    def post_upload(cls, _distance):
        print("forcing the merge into 1 segment...")
        tries = 30
        for i in range(tries + 1):
            try:
                cls.client.indices.forcemerge(
                    index=OPENSEARCH_INDEX, wait_for_completion=True
                )
            except Exception as e:
                if i < tries:  # i is zero indexed
                    print(
                        "Received the following error during retry {}/{} while waiting for ES index to be ready... {}".format(
                            i, tries, e.__str__()
                        )
                    )
                    continue
                else:
                    raise
            _wait_for_es_status(cls.client)
            break
        return {}
