import signal

from support_ai import launcher


def test_ctrl_c_returns_to_menu_and_restart_uses_fresh_app(monkeypatch):
    runs = []
    choices = iter(["invalid", "r", "s"])
    reloads = []
    monkeypatch.setattr(launcher, "reload_application_modules", lambda: reloads.append(True))
    previous = signal.getsignal(signal.SIGINT)

    def run(*args, **kwargs):
        runs.append((args, kwargs))
        # Simulate Uvicorn replaying Ctrl+C after graceful shutdown.
        signal.raise_signal(signal.SIGINT)

    monkeypatch.setattr(launcher.uvicorn, "run", run)
    monkeypatch.setattr("builtins.input", lambda _: next(choices))
    launcher.main()
    assert len(runs) == 2
    assert reloads == [True]
    assert runs[0][0] == ("support_ai.main:create_app",)
    assert runs[0][1]["factory"] is True
    assert signal.getsignal(signal.SIGINT) == previous
