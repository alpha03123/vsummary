"""A turn owns its admission, measured resource scope and recoverable settlement."""
from contextlib import contextmanager
import time
from backend.core.ids import new_ulid
from backend.core.preferences import current_preferences, load_effective_settings
from backend.core.metering import bind_resource_budget
from backend.core.quota import UsageEstimate


class ChatExecution:
    def __init__(self, host, context):
        self.host, self.context, self.id = host, context, new_ulid()
        self.queue = host.chat_queue
        self.terminal = False
        self.queue.enqueue(context, self.id)

    def admission_events(self):
        yield {'request_id': self.id, 'state': 'queued', 'message': '正在等待对话资源'}
        while not self.queue.try_start(self.context, self.id):
            yield None
            time.sleep(self.queue.poll_seconds)
        yield {'request_id': self.id, 'state': 'running', 'message': '正在处理对话'}

    @contextmanager
    def running(self):
        settings = load_effective_settings(self.host.config_path, self.host.root_dir)
        profile = (current_preferences() or {}).get('model_profile')
        estimate = UsageEstimate(units=1, operation_id=self.id, model_profile=profile,
                                 input_tokens=settings.agent_context.window_tokens,
                                 output_tokens=settings.agent_context.reserved_output_tokens)
        reservation = self.host.quota_guard.reserve_job(self.context, 'agent_chat', estimate, self.id)
        self.queue.attach_reservation(self.id, reservation.id, profile)
        with self.queue.running(self.context, self.id) as check, bind_resource_budget(self.host.resource_budget, self.id):
            yield check

    def finish(self, status):
        if self.terminal:
            return
        self.queue.finish(self.id, status)
        self.queue.account(self.id, self.host.quota_guard, self.host.usage_store)
        self.terminal = True
