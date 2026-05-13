import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import BOTH, END, HORIZONTAL, LEFT, RIGHT, VERTICAL, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
DEFAULT_DATA_DIR = ROOT_DIR / "data" / "gui-peer"


class ApiError(RuntimeError):
    pass


def request_json(method, url, payload=None, timeout=5):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"{method} {url} failed with {exc.code}: {body}") from exc
    except URLError as exc:
        raise ApiError(f"{method} {url} failed: {exc.reason}") from exc


class PeerLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Peer File Sharing")
        self.root.geometry("1120x720")
        self.root.minsize(980, 620)

        self.process = None
        self.process_role = None
        self.last_error = ""
        self.file_rows = []
        self.output_queue = queue.Queue()

        self.peer_id_var = StringVar(value="peer1")
        self.peer_ip_var = StringVar(value="YOUR_TAILSCALE_OR_LAN_IP")
        self.peer_port_var = StringVar(value="9000")
        self.discovery_port_var = StringVar(value="9999")
        self.bootstrap_peers_var = StringVar(value="")
        self.data_dir_var = StringVar(value=str(DEFAULT_DATA_DIR))
        self.status_var = StringVar(value="Stopped")
        self.health_var = StringVar(value="No service running")
        self.selected_hash_var = StringVar(value="")

        self._configure_style()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._tick)

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#162033")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#253348")
        style.configure("Muted.TLabel", foreground="#667085")
        style.configure("Status.TLabel", font=("Consolas", 10), foreground="#14532d")
        style.configure("Danger.TLabel", foreground="#991b1b")
        style.configure("Treeview", rowheight=28)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build_layout(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Peer File Sharing", style="Title.TLabel").pack(side=LEFT)
        ttk.Label(
            header,
            text="Native Python launcher for decentralized peer nodes",
            style="Muted.TLabel",
        ).pack(side=RIGHT)

        paned = ttk.PanedWindow(outer, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True)

        self.left = ttk.Frame(paned, padding=14)
        self.right = ttk.Frame(paned, padding=14)
        paned.add(self.left, weight=1)
        paned.add(self.right, weight=3)

        self._build_config_panel()
        self._build_dashboard_panel()

    def _build_config_panel(self):
        ttk.Label(self.left, text="Node Setup", style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.left, text="Run this laptop as a decentralized peer.", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        self.peer_frame = ttk.LabelFrame(self.left, text="Peer config", padding=12)
        self.peer_frame.pack(fill="x", pady=(0, 8))
        self._entry(self.peer_frame, "Peer ID", self.peer_id_var)
        self._entry(self.peer_frame, "This laptop IP", self.peer_ip_var)
        self._entry(self.peer_frame, "Peer port", self.peer_port_var)
        self._entry(self.peer_frame, "Discovery port", self.discovery_port_var)
        self._entry(self.peer_frame, "Bootstrap peers", self.bootstrap_peers_var)
        ttk.Label(
            self.peer_frame,
            text="Optional. Leave blank for LAN discovery and local ports 9000-9010.",
            style="Muted.TLabel",
            wraplength=430,
        ).pack(anchor="w", padx=(16, 0), pady=(0, 4))
        self._folder_entry(self.peer_frame, "Data folder", self.data_dir_var)

        self.button_row = ttk.Frame(self.left)
        self.button_row.pack(fill="x", pady=(14, 0))
        self.start_button = ttk.Button(self.button_row, text="Start service", style="Accent.TButton", command=self.start_service)
        self.start_button.pack(side=LEFT, fill="x", expand=True)
        self.stop_button = ttk.Button(self.button_row, text="Stop", command=self.stop_service)
        self.stop_button.pack(side=LEFT, padx=(8, 0))

        status_frame = ttk.LabelFrame(self.left, text="Service status", padding=12)
        status_frame.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")
        ttk.Label(status_frame, textvariable=self.health_var, style="Muted.TLabel", wraplength=350).pack(anchor="w", pady=(4, 10))
        self.log_text = self._text_box(status_frame, height=9)

    def _build_dashboard_panel(self):
        top = ttk.Frame(self.right)
        top.pack(fill="x")
        ttk.Label(top, text="Network Files", style="Section.TLabel").pack(side=LEFT)
        ttk.Button(top, text="Refresh", command=self.refresh_all).pack(side=RIGHT)

        files_frame = ttk.Frame(self.right)
        files_frame.pack(fill=BOTH, expand=True, pady=(8, 12))

        columns = ("name", "size", "chunks", "peers", "hash")
        self.files_tree = ttk.Treeview(files_frame, columns=columns, show="headings", height=11)
        for column, heading, width in (
            ("name", "Name", 210),
            ("size", "Size", 80),
            ("chunks", "Chunks", 70),
            ("peers", "Peers", 70),
            ("hash", "File hash", 360),
        ):
            self.files_tree.heading(column, text=heading)
            self.files_tree.column(column, width=width, anchor="w")
        files_scroll = ttk.Scrollbar(files_frame, orient=VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=files_scroll.set)
        self.files_tree.pack(side=LEFT, fill=BOTH, expand=True)
        files_scroll.pack(side=RIGHT, fill="y")
        self.files_tree.bind("<<TreeviewSelect>>", self._on_file_select)

        action_row = ttk.Frame(self.right)
        action_row.pack(fill="x", pady=(0, 12))
        ttk.Button(action_row, text="Choose file and publish", command=self.publish_file).pack(side=LEFT)
        ttk.Button(action_row, text="Download selected", command=self.download_selected).pack(side=LEFT, padx=(8, 0))
        ttk.Button(action_row, text="Copy selected hash", command=self._copy_selected_hash).pack(side=LEFT, padx=(8, 0))
        ttk.Label(action_row, textvariable=self.selected_hash_var, style="Muted.TLabel").pack(side=LEFT, padx=(12, 0), fill="x", expand=True)

        lower = ttk.PanedWindow(self.right, orient=HORIZONTAL)
        lower.pack(fill=BOTH, expand=True)

        local_frame = ttk.LabelFrame(lower, text="Local files", padding=10)
        peers_frame = ttk.LabelFrame(lower, text="Peers", padding=10)
        lower.add(local_frame, weight=2)
        lower.add(peers_frame, weight=1)

        self.local_text = self._text_box(local_frame, height=9)
        self.peers_text = self._text_box(peers_frame, height=9)

    def _entry(self, parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=16).pack(side=LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=LEFT, fill="x", expand=True)

    def _folder_entry(self, parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=16).pack(side=LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=LEFT, fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self._choose_data_folder).pack(side=LEFT, padx=(6, 0))

    def _text_box(self, parent, height):
        frame = ttk.Frame(parent)
        frame.pack(fill=BOTH, expand=True)
        text = ttk.Treeview(frame)
        text.destroy()
        import tkinter as tk

        widget = tk.Text(frame, height=height, wrap="word", relief="solid", borderwidth=1, font=("Consolas", 9))
        scroll = ttk.Scrollbar(frame, orient=VERTICAL, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        widget.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill="y")
        widget.configure(state="disabled")
        return widget

    def _choose_data_folder(self):
        selected = filedialog.askdirectory(initialdir=str(ROOT_DIR))
        if selected:
            self.data_dir_var.set(selected)

    def _copy_selected_hash(self):
        file_hash = self.selected_hash_var.get().strip()
        if not file_hash:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(file_hash)
        self._set_status("File hash copied")

    def start_service(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Service running", "Stop the current service before starting another one.")
            return

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC_DIR)
            env["PYTHONUNBUFFERED"] = "1"
            env["PEER_GUI_MODE"] = "gui"

            peer_id = self.peer_id_var.get().strip()
            advertised_ip = self.peer_ip_var.get().strip()
            port = self._require_int(self.peer_port_var.get(), "Peer port")
            discovery_port = self._require_int(self.discovery_port_var.get(), "Discovery port")
            data_dir = Path(self.data_dir_var.get()).expanduser().resolve()
            if not peer_id:
                raise ValueError("Peer ID is required.")
            if not advertised_ip or advertised_ip == "YOUR_TAILSCALE_OR_LAN_IP":
                raise ValueError("Enter this laptop's LAN IP.")
            env.update(
                {
                    "PEER_ID": peer_id,
                    "PEER_HOST": "0.0.0.0",
                    "PEER_ADVERTISE_HOST": advertised_ip,
                    "PEER_PORT": str(port),
                    "DISCOVERY_PORT": str(discovery_port),
                    "BOOTSTRAP_PEERS": self.bootstrap_peers_var.get().strip(),
                    "DATA_DIR": str(data_dir),
                }
            )
            command = [sys.executable, "-m", "peer"]

            self.process = subprocess.Popen(
                command,
                cwd=str(ROOT_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=self._creation_flags(),
            )
            self.process_role = "peer"
            self.last_error = ""
            self._set_status("Starting peer...")
            threading.Thread(target=self._read_process_output, daemon=True).start()
        except Exception as exc:
            self.last_error = str(exc)
            self._set_status("Start failed")
            messagebox.showerror("Start failed", str(exc))

    def stop_service(self):
        if not self.process or self.process.poll() is not None:
            self._set_status("Stopped")
            return
        self._set_status("Stopping...")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self._set_status("Stopped")
        self.health_var.set("No service running")

    def refresh_all(self):
        self._run_background("refresh", self._refresh_all_worker)

    def publish_file(self):
        if self.process_role != "peer" or not self._is_running():
            messagebox.showwarning("Peer required", "Start this laptop as a peer before publishing files.")
            return
        selected = filedialog.askopenfilename(title="Choose a file to publish")
        if not selected:
            return
        self._run_background("publish", lambda: self._publish_worker(Path(selected)))

    def download_selected(self):
        if self.process_role != "peer" or not self._is_running():
            messagebox.showwarning("Peer required", "Start this laptop as a peer before downloading files.")
            return
        file_hash = self.selected_hash_var.get().strip()
        if not file_hash:
            messagebox.showwarning("No file selected", "Select a network file first.")
            return
        self._run_background("download", lambda: self._download_worker(file_hash))

    def _publish_worker(self, source):
        data_dir = Path(self.data_dir_var.get()).expanduser().resolve()
        shared_dir = data_dir / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        target = shared_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        result = request_json("POST", self._local_peer_url("/publish"), {"path": str(target)})
        self.root.after(0, lambda: self._set_status(f"Published {result['name']}"))
        self._refresh_all_worker()

    def _download_worker(self, file_hash):
        result = request_json("POST", self._local_peer_url("/download"), {"file_hash": file_hash})
        self.root.after(0, lambda: self._set_status(f"Downloaded to {result['saved_to']}"))
        self._refresh_all_worker()

    def _refresh_all_worker(self):
        if self.process_role == "peer":
            files = request_json("GET", self._local_peer_url("/files")).get("files", [])
            local = request_json("GET", self._local_peer_url("/local"))
            peers = request_json("GET", self._local_peer_url("/peers")).get("peers", [])
        else:
            files = []
            peers = []
            local = {"shared": [], "downloads": [], "chunks": []}
        self.root.after(0, lambda: self._render_data(files, peers, local))

    def _render_data(self, files, peers, local):
        self.file_rows = files
        self.files_tree.delete(*self.files_tree.get_children())
        for index, item in enumerate(files):
            self.files_tree.insert(
                "",
                END,
                iid=str(index),
                values=(
                    item.get("name", ""),
                    item.get("size", ""),
                    len(item.get("chunks", [])),
                    len(item.get("peers", {})),
                    item.get("file_hash", ""),
                ),
            )

        local_lines = [
            "Shared files:",
            *[f"  {item}" for item in local.get("shared", [])],
            "",
            "Downloaded files:",
            *[f"  {item}" for item in local.get("downloads", [])],
            "",
            f"Chunks stored: {len(local.get('chunks', []))}",
        ]
        self._replace_text(self.local_text, "\n".join(local_lines))

        peer_lines = []
        for peer in peers:
            peer_lines.append(f"{peer.get('peer_id')}  {peer.get('host')}:{peer.get('port')}  last_seen={peer.get('last_seen')}")
        self._replace_text(self.peers_text, "\n".join(peer_lines) if peer_lines else "No peers discovered yet.")

    def _on_file_select(self, _event):
        selection = self.files_tree.selection()
        if not selection:
            self.selected_hash_var.set("")
            return
        index = int(selection[0])
        if index < len(self.file_rows):
            self.selected_hash_var.set(self.file_rows[index].get("file_hash", ""))

    def _run_background(self, label, worker):
        def run():
            try:
                self.root.after(0, lambda: self._set_status(f"{label.capitalize()} running..."))
                worker()
            except Exception as exc:
                self.last_error = str(exc)
                self.root.after(0, lambda: self._set_status(f"{label.capitalize()} failed"))
                self.root.after(0, lambda: messagebox.showerror(f"{label.capitalize()} failed", str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def _tick(self):
        self._drain_output()
        if self.process and self.process.poll() is not None:
            if self.status_var.get() not in ("Stopped", "Start failed"):
                code = self.process.returncode
                self._set_status(f"Stopped with exit code {code}")
                self.health_var.set(self.last_error or "Service process exited.")
        elif self.process and self.process.poll() is None:
            self._poll_health_async()
        self.root.after(1000, self._tick)

    def _poll_health_async(self):
        def run():
            try:
                health = request_json("GET", self._local_peer_url("/health"), timeout=1)
                expected_peer_id = self.peer_id_var.get().strip()
                actual_peer_id = health.get("peer_id")
                if expected_peer_id and actual_peer_id and actual_peer_id != expected_peer_id:
                    message = (
                        f"Port {self.peer_port_var.get().strip()} is serving {actual_peer_id}, "
                        f"not {expected_peer_id}. Use a different peer port or stop the other peer."
                    )
                    self.root.after(0, lambda: self.health_var.set(message))
                    self.root.after(0, lambda: self.status_var.set("Peer port conflict"))
                    return
                self.root.after(0, lambda: self.health_var.set(f"Healthy: {health}"))
                self.root.after(0, lambda: self.status_var.set("Running as peer"))
            except Exception as exc:
                self.root.after(0, lambda: self.health_var.set(f"Starting or unreachable: {exc}"))

        threading.Thread(target=run, daemon=True).start()

    def _read_process_output(self):
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.output_queue.put(line.rstrip())

    def _drain_output(self):
        lines = []
        while True:
            try:
                lines.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        if not lines:
            return
        self.log_text.configure(state="normal")
        for line in lines:
            self.log_text.insert(END, line + "\n")
            if "failed" in line.lower() or "error" in line.lower():
                self.last_error = line
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _replace_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", END)
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _set_status(self, value):
        self.status_var.set(value)

    def _is_running(self):
        return self.process is not None and self.process.poll() is None

    def _require_int(self, value, label):
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if parsed < 1 or parsed > 65535:
            raise ValueError(f"{label} must be between 1 and 65535.")
        return parsed

    def _local_peer_url(self, path):
        return f"http://127.0.0.1:{self.peer_port_var.get().strip()}{path}"

    def _creation_flags(self):
        if os.name == "nt":
            return subprocess.CREATE_NEW_PROCESS_GROUP
        return 0

    def _on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Quit peer launcher", "Stop the running service and close the launcher?"):
                return
            self.stop_service()
        self.root.destroy()


def main():
    root = Tk()
    PeerLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
