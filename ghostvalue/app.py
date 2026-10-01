"""Run with python app.py on 64-bit Windows Python."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from .core import Memory, add_budget, backup_save, game_pids, log_action
from .lua_memory import LuaReader, set_gold_auto
from .spell_budget import add_spell_budget
from .permanent_patch import installed_profile


class App:
    def __init__(self, root):
        self.root, self.memory, self.candidates = root, None, None
        self.last_value, self.scan_kind, self.busy = None, None, False
        self.results = queue.Queue()
        self.permanent = installed_profile()
        root.title('GhostValue 0.4 · Kingdom Rush Genesis')
        root.geometry('760x660')
        root.minsize(720, 620)
        panel = ttk.Frame(root, padding=24)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Kingdom Rush Genesis', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='金币自动定位 · 永久升级额度补丁已安装' if self.permanent else '金币自动定位 · 升级额度仅在本次游戏运行中生效').pack(anchor='w', pady=(4, 18))
        bar = ttk.Frame(panel)
        bar.pack(fill='x')
        ttk.Button(bar, text='连接游戏', command=self.connect).pack(side='left')
        ttk.Button(bar, text='备份存档', command=self.backup).pack(side='left', padx=8)
        self.status = tk.StringVar(value='尚未连接游戏')
        ttk.Label(panel, textvariable=self.status, wraplength=620).pack(anchor='w', pady=12)
        automatic = ttk.LabelFrame(panel, text='局内金币', padding=16)
        automatic.pack(fill='x')
        ttk.Label(automatic, text='进入关卡即可设置，无需暂停。修改一次后，金币仍正常增加和扣除。', wraplength=620).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 12))
        ttk.Label(automatic, text='目标金币').grid(row=1, column=0)
        self.auto_target = tk.StringVar(value='50000')
        ttk.Entry(automatic, textvariable=self.auto_target, width=12).grid(row=1, column=1, padx=8)
        ttk.Button(automatic, text='读取当前金币', command=lambda: self.automatic_gold(False)).grid(row=1, column=2, padx=4)
        ttk.Button(automatic, text='设置金币', command=lambda: self.automatic_gold(True)).grid(row=1, column=3, padx=4)
        self.auto_status = tk.StringVar(value='尚未读取当前关卡')
        ttk.Label(automatic, textvariable=self.auto_status).grid(row=2, column=0, columnspan=4, sticky='w', pady=(12, 0))
        self.manual_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='显示手动筛选（备用）', variable=self.manual_visible, command=self.toggle_manual).pack(anchor='w', pady=8)
        box = self.manual_box = ttk.LabelFrame(panel, text='手动定位', padding=16)
        ttk.Label(box, text='1. 进入关卡并暂停，输入当前金币。\n2. 扫描后回到游戏消费或获得金币，暂停并输入新数值，继续筛选。', wraplength=580).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 12))
        self.value = tk.StringVar()
        self.kind = tk.StringVar(value='double')
        ttk.Entry(box, textvariable=self.value, width=14).grid(row=1, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.kind, values=('double', 'int32'), state='readonly', width=10).grid(row=1, column=1, padx=8)
        ttk.Button(box, text='重新扫描', command=lambda: self.scan(True)).grid(row=1, column=2, padx=4)
        ttk.Button(box, text='继续筛选', command=lambda: self.scan(False)).grid(row=1, column=3, padx=4)
        self.count = tk.StringVar(value='候选地址：尚未扫描。默认尝试 Lua 常见的 double 数值。')
        ttk.Label(box, textvariable=self.count, wraplength=570).grid(row=2, column=0, columnspan=4, sticky='w', pady=12)
        self.target = tk.StringVar(value='50000')
        ttk.Entry(box, textvariable=self.target, width=14).grid(row=3, column=0, sticky='w')
        ttk.Button(box, text='设置金币', command=self.write).grid(row=3, column=1, columnspan=2, sticky='w', padx=8)
        ttk.Label(box, text='仅剩一个候选时允许写入；换关或重启游戏后必须重新扫描。', wraplength=580).grid(row=4, column=0, columnspan=4, sticky='w', pady=(12, 0))
        upgrades = self.upgrades_box = ttk.LabelFrame(panel, text='升级点额度', padding=16)
        upgrades.pack(fill='x', pady=(16, 0))
        self.bonus = tk.StringVar(value='50')
        ttk.Label(upgrades, text='增加点数：').grid(row=0, column=0)
        ttk.Entry(upgrades, textvariable=self.bonus, width=8).grid(row=0, column=1, padx=6)
        self.tower_button = ttk.Button(upgrades, text='增加防御塔额度', command=lambda: self.budget('tower'))
        self.tower_button.grid(row=0, column=2, padx=4)
        self.hero_button = ttk.Button(upgrades, text='增加英雄额度', command=lambda: self.budget('hero'))
        self.hero_button.grid(row=0, column=3, padx=4)
        self.spell_button = ttk.Button(upgrades, text='增加法术额度', command=lambda: self.budget('spell'))
        self.spell_button.grid(row=1, column=2, columnspan=2, sticky='w', padx=4, pady=(8, 0))
        help_text = '分别增加所有战役阶段、英雄等级或所有法术的升级额度。\n刚修改后显示可能不刷新，购买或重置后再核对。\n临时额度重启失效，已购买升级仍可能保存，造成负数。'
        if self.permanent:
            for button in (self.tower_button, self.hero_button, self.spell_button):
                button.configure(state='disabled')
            help_text = '游戏启动时自动加载额外额度，无需打开修改器。\n已禁用临时加点，避免重启后再次出现额度不足。\nSteam 更新或验证文件可能移除补丁，需要重新检查和适配。'
        ttk.Label(upgrades, text=help_text, wraplength=610).grid(row=2, column=0, columnspan=4, sticky='w', pady=(12, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def error(self, exc):
        messagebox.showerror('操作未完成', str(exc))

    def toggle_manual(self):
        if self.manual_visible.get():
            self.manual_box.pack(fill='x', before=self.upgrades_box)
            self.root.geometry('760x920')
        else:
            self.manual_box.pack_forget()
            self.root.geometry('760x660')

    def automatic_gold(self, write):
        if self.busy:
            return
        try:
            if not self.memory or not self.memory.alive():
                raise RuntimeError('请先连接游戏')
            target = int(self.auto_target.get()) if write else None
            self.busy = True
            self.status.set('正在识别当前关卡，首次定位可能需要几秒……')
            def work():
                try:
                    result = set_gold_auto(self.memory, target) if write else LuaReader(self.memory).locate_gold()
                    self.results.put(('auto_gold', result, write))
                except Exception as exc:
                    self.results.put(('error', exc))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            self.error(exc)

    def connect(self):
        if self.busy:
            return
        try:
            pids = game_pids()
            if len(pids) != 1:
                raise RuntimeError('请确保只运行一个 Kingdom Rush Genesis 游戏进程')
            if self.memory:
                self.memory.close()
            self.memory = Memory(pids[0])
            self.candidates = None
            self.count.set('候选地址：尚未扫描')
            self.auto_status.set('尚未读取当前关卡')
            self.status.set(f'已连接游戏（进程 {pids[0]}），进入关卡即可设置金币。')
        except Exception as exc:
            self.error(exc)

    def backup(self):
        try:
            path = backup_save()
            self.status.set('已备份并校验：' + str(path))
        except Exception as exc:
            self.error(exc)

    def scan(self, fresh):
        if self.busy:
            return
        try:
            if not self.memory:
                raise RuntimeError('请先连接游戏')
            if not fresh and (self.candidates is None or self.kind.get() != self.scan_kind):
                raise RuntimeError('请先重新扫描；筛选时不能更改数值类型')
            value, kind = int(self.value.get()), self.kind.get()
            candidates = None if fresh else self.candidates
            self.busy = True
            self.status.set('正在读取游戏内存，请稍候……')
            def work():
                try:
                    self.results.put(('ok', self.memory.scan(value, kind, candidates), value, kind))
                except Exception as exc:
                    self.results.put(('error', exc))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            self.error(exc)

    def poll(self):
        try:
            result = self.results.get_nowait()
            self.busy = False
            if result[0] == 'auto_gold':
                info, wrote = result[1:]
                self.auto_status.set(f'第 {info["level"]} 关 · 金币 {info["value"]}')
                if wrote:
                    self.status.set(f'已写入 {info["requested"]}，游戏运行中金币已继续变化，当前 {info["value"]}。' if info.get('changed_after_write') else '金币已设置，读回确认成功，存档已备份。')
                else:
                    self.status.set('已自动识别当前金币，无需手动筛选。')
            elif result[0] == 'budget':
                self.status.set('已增加升级额度并读回确认，存档已备份。请在游戏内购买或重置后核对点数。')
            elif result[0] == 'error':
                self.status.set('操作未完成；请查看错误提示。')
                self.candidates = None
                self.error(result[1])
            else:
                _, self.candidates, self.last_value, self.scan_kind = result
                self.count.set(f'候选地址：{len(self.candidates)} 个')
                self.status.set('筛选完成。唯一候选仍需实际验证是否为金币。' if len(self.candidates) == 1 else '请改变游戏内金币后继续筛选；零候选时重新扫描或换类型。')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def budget(self, kind):
        if self.busy:
            return
        try:
            if installed_profile():
                raise RuntimeError('已安装永久额度补丁，临时加点已禁用。修改永久额度需要在游戏关闭后更新补丁。')
            if not self.memory or not self.memory.alive():
                raise RuntimeError('请先连接正在运行的游戏')
            amount = int(self.bonus.get())
            if not 1 <= amount <= 100:
                raise ValueError('每次请输入 1 到 100 点')
            self.busy = True
            self.status.set('正在核对完整升级配置并备份存档……')
            def work():
                try:
                    path = add_spell_budget(self.memory, amount) if kind == 'spell' else add_budget(self.memory, kind, amount)
                    self.results.put(('budget', path))
                except Exception as exc:
                    self.results.put(('error', exc))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            self.error(exc)

    def write(self):
        if self.busy:
            return
        try:
            if not self.candidates or len(self.candidates) != 1:
                raise RuntimeError('请先筛选到唯一候选地址')
            value = int(self.target.get())
            if not messagebox.askokcancel('首次定位仍需验证', f'将候选位置的 {self.last_value} 改为 {value}。\n请确保仍在同一关卡且游戏暂停；修改后核对游戏金币。'):
                return
            backup = backup_save()
            log_action('gold_write_attempt', pid=self.memory.pid, address=hex(self.candidates[0]), old=self.last_value, new=value, backup=str(backup))
            self.memory.write_verified(self.candidates[0], self.last_value, value, self.scan_kind)
            self.last_value = value
            log_action('gold_write_readback_verified', new=value)
            self.status.set('已写入并读回确认。请核对游戏金币显示及购买效果；这一步尚未证明候选就是金币。')
        except Exception as exc:
            self.error(exc)

    def close(self):
        if self.busy:
            messagebox.showinfo('正在处理', '请等待本次操作结束后关闭窗口。')
            return
        if self.memory:
            self.memory.close()
        self.root.destroy()


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
