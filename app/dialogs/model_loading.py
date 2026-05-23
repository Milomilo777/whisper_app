"""ModelLoadingDialog — modal Toplevel shown while the Whisper model
loads on first transcribe.

Companion to :mod:`app.dialogs.model_download` (which drives the
*download* of the model). This dialog is the much simpler sibling:
the bytes are already on disk; we only need to wait for a worker
subprocess to import faster-whisper and load the weights into RAM.

Lifecycle:

* Caller constructs the dialog and immediately calls
  ``self.wait_window(dialog)``.
* While the dialog is up, the App's :func:`poll` loop will see a
  ``ready`` event for the freshly-spawned worker and, via the
  ``_main_thread_calls`` queue, mark this dialog's
  :attr:`success` ``True`` then call :meth:`destroy`.
* If the user clicks Cancel first, :attr:`success` stays ``False``
  and the caller is responsible for tearing down the worker.

The dialog itself does NOT spawn the worker or talk to the model
manager — that's the TranscriptionService's job. We just provide a
modal UI surface during the wait.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ModelLoadingDialog(tk.Toplevel):
    """Modal "Loading Whisper model…" dialog with an indeterminate bar.

    Attributes
    ----------
    success : bool
        ``True`` when the model finished loading (caller flips this
        from outside, typically from the worker-event poll loop on
        the Tk main thread). ``False`` if the user clicks Cancel or
        closes the window via the WM_DELETE_WINDOW button.
    """

    def __init__(self, master: "tk.Tk | tk.Toplevel") -> None:
        super().__init__(master)
        self.title("Loading Whisper model")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.success: bool = False

        body = ttk.Frame(self, padding=18)
        body.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            body,
            text="Loading the Whisper model — this takes a few seconds…",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            body,
            text=(
                "The model loads once per session. "
                "Subsequent transcriptions start instantly."
            ),
            foreground="#666",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self.pb = ttk.Progressbar(body, length=420, mode="indeterminate")
        self.pb.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        # .start(N) ticks the indeterminate bar every N ms so the
        # user has visual confirmation the app isn't frozen.
        self.pb.start(10)

        self.cancel_btn = ttk.Button(body, text="Cancel", command=self.cancel)
        self.cancel_btn.grid(row=3, column=0, sticky="e")

        body.columnconfigure(0, weight=1)

        # Centre on parent. update_idletasks first so winfo_width
        # returns the real laid-out width rather than 1.
        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

        # grab_set last — once the layout is settled. Some headless
        # test envs can't grab; that's fine, we just skip.
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def cancel(self) -> None:
        """User pressed Cancel (or closed the window).

        We do NOT kill the worker from here — the caller owns the
        worker lifecycle and reads :attr:`success` after
        ``wait_window`` returns to decide what to do.
        """
        self.success = False
        try:
            self.pb.stop()
        except tk.TclError:
            pass
        try:
            self.cancel_btn.configure(state="disabled")
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def mark_success_and_close(self) -> None:
        """Called from the worker-event poll loop when the spawned
        worker emits its ``ready`` event. Sets :attr:`success`
        ``True`` then closes the dialog so ``wait_window`` returns
        in the caller.
        """
        self.success = True
        try:
            self.pb.stop()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
