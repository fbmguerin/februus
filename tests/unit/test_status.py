"""Tests for the in-memory status of the station."""

import threading

from februus.core.status import SessionStatus, Status


def test_starts_idle():
    assert Status().snapshot() == SessionStatus(id=0, state="idle")


def test_start_numbers_the_sessions_and_keeps_the_signatures():
    status = Status()
    assert status.start() == 1
    status.update(signatures="ClamAV 1", state="result", verdict="green", files_done=3)
    assert status.start() == 2
    shown = status.snapshot()
    assert (shown.state, shown.verdict, shown.files_done) == ("scanning", None, 0)
    assert shown.signatures == "ClamAV 1"


def test_extra_keys_are_kept_through_the_sessions():
    status = Status()
    status.set_extra_keys(1)
    assert status.snapshot().extra_keys == 1
    status.start()
    status.update(state="result", verdict="green")
    status.close()
    assert status.snapshot().extra_keys == 1
    status.set_extra_keys(0)
    assert status.snapshot().extra_keys == 0


def test_close_goes_back_to_idle_after_the_result():
    for state in ("result", "aborted"):
        status = Status()
        status.start()
        status.update(state=state, verdict="red", signatures="ClamAV 1", problems=("x.y",))
        status.close()
        assert status.snapshot() == SessionStatus(id=1, state="idle", signatures="ClamAV 1")


def test_close_leaves_a_running_session_alone():
    status = Status()
    status.start()
    status.update(state="inspecting")
    status.close()
    assert status.snapshot().state == "inspecting"


def test_snapshot_is_never_changed_afterwards():
    status = Status()
    status.start()
    before = status.snapshot()
    status.update(files_done=5)
    assert before.files_done == 0


def test_threads_can_write_and_read():
    status = Status()
    status.start()

    def work():
        for i in range(500):
            status.update(files_done=i)

    thread = threading.Thread(target=work)
    thread.start()
    while thread.is_alive():
        assert 0 <= status.snapshot().files_done < 500
    thread.join()
    assert status.snapshot().files_done == 499
