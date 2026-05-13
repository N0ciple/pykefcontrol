import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pykefcontrol.kef_connector import KefAsyncConnector, KefConnector


class SourceNormalizationTest(unittest.TestCase):
    def test_sync_source_setter_normalizes_optic_alias(self):
        speaker = object.__new__(KefConnector)
        speaker.host = "192.0.2.1"
        speaker._speaker_model = "LS50WII"

        with patch("pykefcontrol.kef_connector.requests.post") as post:
            post.return_value.__enter__.return_value.json.return_value = {}

            speaker.source = "optic"

        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            payload["value"],
            {"type": "kefPhysicalSource", "kefPhysicalSource": "optical"},
        )

    def test_sync_source_setter_keeps_optical_source(self):
        speaker = object.__new__(KefConnector)
        speaker.host = "192.0.2.1"
        speaker._speaker_model = "LS50WII"

        with patch("pykefcontrol.kef_connector.requests.post") as post:
            post.return_value.__enter__.return_value.json.return_value = {}

            speaker.source = "optical"

        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            payload["value"],
            {"type": "kefPhysicalSource", "kefPhysicalSource": "optical"},
        )

    def test_async_set_source_normalizes_optic_alias(self):
        async def run_test():
            speaker = object.__new__(KefAsyncConnector)
            speaker._set_data = AsyncMock()

            await speaker.set_source("optic")

            payload = speaker._set_data.call_args.args[0]
            self.assertEqual(
                payload["value"],
                {"type": "kefPhysicalSource", "kefPhysicalSource": "optical"},
            )

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
