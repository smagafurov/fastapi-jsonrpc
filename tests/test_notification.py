import asyncio
import collections
import time
from typing import Dict

import pytest
from fastapi import Body


class ExecutionTracker:
    def __init__(self):
        self.executions = []
        self.last_execution_time = 0

    def record(self, method_name, delay):
        self.executions.append((method_name, delay))
        self.last_execution_time = time.monotonic()


@pytest.fixture
def tracker():
    return ExecutionTracker()


@pytest.fixture
def ep(ep, tracker):
    @ep.method()
    async def delayed_method(
        delay: float = Body(..., ge=0),
        message: str = Body(...),
    ) -> dict:
        start_time = time.monotonic()
        await asyncio.sleep(delay)
        tracker.record("delayed_method", delay)
        return {"message": message, "execution_time": time.monotonic() - start_time}

    @ep.method()
    async def instant_method(
        message: str = Body(...),
    ) -> Dict[str, str]:
        tracker.record("instant_method", 0)
        return {"message": message}

    return ep


def test_regular_request__no_background(app, json_request, tracker):
    start_time = time.monotonic()
    delay = 0.5

    # Запрос с ID (синхронный)
    response = json_request(
        {
            "jsonrpc": "2.0",
            "method": "delayed_method",
            "params": {"delay": delay, "message": "sync request"},
            "id": 1
        }
    )

    execution_time = time.monotonic() - start_time

    # Проверяем, что время выполнения больше чем задержка (т.е. запрос ждал завершения)
    assert execution_time >= delay
    assert response == {
        "jsonrpc": "2.0",
        "result": {
            "message": "sync request",
            "execution_time": pytest.approx(delay, abs=0.1)
        },
        "id": 1
    }
    assert len(tracker.executions) == 1
    assert tracker.executions[0][0] == "delayed_method"


def test_single_request__notification_in_background(app, app_client, tracker, ep_wait_all_requests_done):
    start_time = time.monotonic()
    delay = 0.5

    # Запрос без ID (уведомление, должен выполниться асинхронно)
    response = app_client.post(
        "/api/v1/jsonrpc",
        json={
            "jsonrpc": "2.0",
            "method": "delayed_method",
            "params": {"delay": delay, "message": "async notification"}
        }
    )

    execution_time = time.monotonic() - start_time

    # Проверяем, что время выполнения меньше чем задержка (т.е. запрос не ждал завершения)
    assert execution_time < delay
    assert response.status_code == 200
    assert response.content == b''  # Пустой ответ для уведомления

    # Ждем, чтобы убедиться что задача завершилась
    ep_wait_all_requests_done()

    # Проверяем, что функция действительно была выполнена
    assert len(tracker.executions) == 1
    assert tracker.executions[0][0] == "delayed_method"


def test_batch_request__notification_in_background(app, app_client, tracker, ep_wait_all_requests_done):
    start_time = time.monotonic()
    delay1 = 0.5
    delay2 = 0.3

    # Batch-запрос с обычными запросами и уведомлениями
    response = app_client.post(
        "/api/v1/jsonrpc",
        json=[
            # Обычный запрос
            {
                "jsonrpc": "2.0",
                "method": "delayed_method",
                "params": {"delay": delay1, "message": "sync request 1"},
                "id": 1
            },
            # Уведомление
            {
                "jsonrpc": "2.0",
                "method": "delayed_method",
                "params": {"delay": delay2, "message": "notification 1"}
            },
            # Еще один обычный запрос
            {
                "jsonrpc": "2.0",
                "method": "instant_method",
                "params": {"message": "sync request 2"},
                "id": 2
            },
            # Еще одно уведомление
            {
                "jsonrpc": "2.0",
                "method": "instant_method",
                "params": {"message": "notification 2"}
            }
        ]
    )

    execution_time = time.monotonic() - start_time

    # Проверяем, что время выполнения больше чем максимальная задержка среди обычных запросов
    assert execution_time >= delay1
    assert response.status_code == 200

    result = response.json()
    # В ответе должны быть только запросы с ID
    assert len(result) == 2

    # Проверяем содержимое ответов (порядок может быть любым)
    result_dict = {item["id"]: item for item in result}

    assert result_dict[1]["jsonrpc"] == "2.0"
    assert result_dict[1]["result"]["message"] == "sync request 1"
    assert float(result_dict[1]["result"]["execution_time"]) >= delay1

    assert result_dict[2]["jsonrpc"] == "2.0"
    assert result_dict[2]["result"]["message"] == "sync request 2"

    # Ждем, чтобы убедиться что все задачи завершились
    ep_wait_all_requests_done()

    # Проверяем что все функции действительно были выполнены (всего 4)
    assert len(tracker.executions) == 4

    # Проверяем типы выполненных функций (должны быть 2 delayed_method и 2 instant_method)
    method_counts = collections.Counter((x[0] for x in tracker.executions))

    assert method_counts["delayed_method"] == 2
    assert method_counts["instant_method"] == 2