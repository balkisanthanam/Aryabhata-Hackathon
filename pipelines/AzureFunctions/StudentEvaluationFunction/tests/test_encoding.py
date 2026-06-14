"""Quick test to understand Python SDK queue message encoding behavior."""
import json
import base64
from azure.storage.queue import QueueClient

with open('local.settings.json') as f:
    settings = json.load(f)
conn = settings['Values']['AzureWebJobsStorage']

# 1. Send with DEFAULT SDK settings (should be base64)
qc_default = QueueClient.from_connection_string(conn, 'test-encoding-default')
try:
    qc_default.create_queue()
except:
    pass
# Clear existing messages
qc_default.clear_messages()
qc_default.send_message('test-uuid-12345')

# 2. Read with raw (no-decode) client to see what's actually in queue
qc_raw = QueueClient.from_connection_string(conn, 'test-encoding-default',
    message_encode_policy=None, message_decode_policy=None)
msgs = qc_raw.peek_messages(max_messages=1)
for m in msgs:
    raw = m.content
    print(f"Sent with DEFAULT policy, RAW peek: '{raw}'")
    expected_b64 = base64.b64encode(b'test-uuid-12345').decode()
    print(f"Expected if base64 encoded: '{expected_b64}'")
    print(f"Is base64 encoded: {raw == expected_b64}")

# 3. Send with EXPLICIT None encode policy
qc_none = QueueClient.from_connection_string(conn, 'test-encoding-none',
    message_encode_policy=None, message_decode_policy=None)
try:
    qc_none.create_queue()
except:
    pass
qc_none.clear_messages()
qc_none.send_message('test-uuid-67890')
msgs2 = qc_none.peek_messages(max_messages=1)
for m in msgs2:
    print(f"\nSent with None policy, RAW peek: '{m.content}'")

# Cleanup test queues
qc_default.delete_queue()
qc_none.delete_queue()
print("\nDone. Test queues cleaned up.")
