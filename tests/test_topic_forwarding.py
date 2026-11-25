import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from filters.sender_filter import SenderFilter
from utils.common import extract_topic_id


class TopicExtractionTests(unittest.TestCase):
    def test_normal_chat_and_general_topic(self):
        for reply in (
            None,
            SimpleNamespace(forum_topic=False, reply_to_msg_id=42),
            SimpleNamespace(forum_topic=True, reply_to_msg_id=1),
        ):
            with self.subTest(reply=reply):
                self.assertIsNone(extract_topic_id(SimpleNamespace(reply_to=reply)))

    def test_topic_root_and_replies(self):
        for reply in (
            SimpleNamespace(forum_topic=True, reply_to_msg_id=42),
            SimpleNamespace(forum_topic=True, reply_to_top_id=42, reply_to_msg_id=100),
        ):
            with self.subTest(reply=reply):
                self.assertEqual(extract_topic_id(SimpleNamespace(reply_to=reply)), 42)


class TopicDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_and_files_are_sent_to_the_bound_topic(self):
        for method, api_method in (
            ("_send_message_with_topic_retry", "send_message"),
            ("_send_file_with_topic_retry", "send_file"),
        ):
            with self.subTest(method=method):
                send = AsyncMock(return_value="sent")
                client = SimpleNamespace(**{api_method: send})
                result = await getattr(SenderFilter(), method)(
                    client, SimpleNamespace(id=7, target_topic_id=42), -100123, "payload"
                )
                self.assertEqual(result, "sent")
                send.assert_awaited_once_with(-100123, "payload", reply_to=42)

    async def test_plain_channels_have_no_topic_parameter(self):
        for method, api_method in (
            ("_send_message_with_topic_retry", "send_message"),
            ("_send_file_with_topic_retry", "send_file"),
        ):
            with self.subTest(method=method):
                send = AsyncMock()
                client = SimpleNamespace(**{api_method: send})
                await getattr(SenderFilter(), method)(
                    client, SimpleNamespace(id=7, target_topic_id=None), -100123, "payload"
                )
                send.assert_awaited_once_with(-100123, "payload", reply_to=None)

    async def test_deleted_topic_is_not_resent_into_main_chat(self):
        for method, api_method in (
            ("_send_message_with_topic_retry", "send_message"),
            ("_send_file_with_topic_retry", "send_file"),
        ):
            with self.subTest(method=method):
                send = AsyncMock(side_effect=[ValueError("TOPIC_DELETED"), "sent"])
                client = SimpleNamespace(**{api_method: send})
                with self.assertRaisesRegex(ValueError, "TOPIC_DELETED"):
                    await getattr(SenderFilter(), method)(
                        client, SimpleNamespace(id=7, target_topic_id=42), -100123, "payload"
                    )
                send.assert_awaited_once_with(-100123, "payload", reply_to=42)

    async def test_unknown_failure_is_not_resent(self):
        for method, api_method in (
            ("_send_message_with_topic_retry", "send_message"),
            ("_send_file_with_topic_retry", "send_file"),
        ):
            with self.subTest(method=method):
                send = AsyncMock(side_effect=TimeoutError("connection lost"))
                client = SimpleNamespace(**{api_method: send})
                with self.assertRaises(TimeoutError):
                    await getattr(SenderFilter(), method)(
                        client, SimpleNamespace(id=7, target_topic_id=42), -100123, "payload"
                    )
                send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
