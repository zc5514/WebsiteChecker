import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, ttk, Checkbutton, IntVar
import requests
import re
import threading
from queue import Queue, Empty
import concurrent.futures
import time
import pyperclip  # 用于跨平台剪贴板操作
import base64


class WebsiteChecker:
    def __init__(self, master):
        self.master = master
        master.title("批量网站返回值测试 (订阅)")
        master.geometry("700x700")
        # 主机地址输入区域
        tk.Label(master, text="请输入要测试的网站地址（每行一个）:").pack(pady=5)
        self.host_text = scrolledtext.ScrolledText(master, height=10, width=80)
        self.host_text.pack(pady=5)
        # 检索字符串输入区域
        tk.Label(master, text="检索字符串（默认为 {name:）:").pack(pady=5)
        self.search_entry = tk.Entry(master, width=50)
        self.search_entry.pack(pady=5)
        self.search_entry.insert(0, "{name:")
        # 增加一个复选框，用于选择是否进行base64解码
        self.decode_var = IntVar(value=0) # 用于跟踪是否选中Base64解码
        self.decode_checkbutton = Checkbutton(master, text="Base64解码", variable=self.decode_var,command=self.toggle_search_string)
        self.decode_checkbutton.pack()
        # 复合检测复选框
        self.composite_check_var = IntVar(value=0)  # 用于跟踪是否选中BPB面板
        self.composite_check = Checkbutton(master, text="BPB面板检测", variable=self.composite_check_var,command=self.toggle_bpb_string)
        self.composite_check.pack()
        # 并发线程数设置
        thread_frame = tk.Frame(master)
        thread_frame.pack(pady=5)
        tk.Label(thread_frame, text="并发线程数:").pack(side=tk.LEFT, padx=5)
        self.thread_var = tk.StringVar(value="20")
        self.thread_spinbox = tk.Spinbox(thread_frame, from_=1, to=100, textvariable=self.thread_var, width=5)
        self.thread_spinbox.pack(side=tk.LEFT, padx=5)
        # 超时时间设置
        timeout_frame = tk.Frame(master)
        timeout_frame.pack(pady=5)
        tk.Label(timeout_frame, text="请求超时(秒):").pack(side=tk.LEFT, padx=5)
        self.timeout_var = tk.StringVar(value="8")
        self.timeout_spinbox = tk.Spinbox(timeout_frame, from_=1, to=30, textvariable=self.timeout_var, width=5)
        self.timeout_spinbox.pack(side=tk.LEFT, padx=5)
        # 按钮区域
        button_frame = tk.Frame(master)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="从文件导入", command=self.import_hosts).pack(side=tk.LEFT, padx=5)
        self.start_check_button = tk.Button(button_frame, text="开始检测", command=self.start_check)
        self.start_check_button.pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="删除无效结果", command=self.clear_results).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="复制有效网址", command=self.copy_results).pack(side=tk.LEFT, padx=5)
        # 进度条
        self.progress = ttk.Progressbar(master, length=600, mode='determinate')
        self.progress.pack(pady=5)
        # 状态标签
        self.status_label = tk.Label(master, text="")
        self.status_label.pack(pady=5)

        # 结果显示区域
        tk.Label(master, text="检测结果:").pack(pady=5)
        self.result_text = scrolledtext.ScrolledText(master, height=15, width=80)
        self.result_text.pack(pady=5)
        # 线程同步锁
        self.result_lock = threading.Lock()

    def import_hosts(self):
        """从文件导入主机地址"""
        filename = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt")])
        if filename:
            with open(filename, 'r', encoding='utf-8') as file:
                self.host_text.delete('1.0', tk.END)
                self.host_text.insert(tk.END, file.read())

    def copy_results(self):

        # 获取有效结果文本
        result_text = self.result_text.get('1.0', tk.END)
        # 提取所有主机地址（匹配 ✅ 或 ❌ 开头的行）
        hosts = []
        for line in result_text.split('\n'):
            if line.startswith(('✅')):
                # 提取主机地址（从第3个字符开始，直到第一个 ' - ' 之前）
                parts = line.split(' - ')
                if parts:
                    hosts.append(parts[0][2:].strip())
        # 如果有主机地址，复制到剪贴板
        if hosts:
            # 使用pyperclip跨平台复制
            pyperclip.copy('\n'.join(hosts))
            messagebox.showinfo("复制成功", f"已复制 {len(hosts)} 个主机地址到剪贴板")
        else:
            messagebox.showwarning("复制失败", "没有可复制的主机地址")

    def toggle_search_string(self):
        """根据Checkbutton的状态更改检索字符串"""
        if self.decode_var.get():
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, "vless://")
        else:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, "{name:")

    def toggle_bpb_string(self):
        """根据Checkbutton的状态更改检索字符串"""
        if self.composite_check_var.get():
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, "vless://")
            self.decode_checkbutton.select()
        else:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, "{name:")
            self.decode_checkbutton.deselect()
    def check_website(self, host, search_string, timeout, decode_base64,composite_check):
        """检查单个网站"""
        try:
            # 如果选中复合检测，则在网址后添加指定的子路径
            if composite_check:
                host += "/sub/89b3cbba-e6ac-485a-9481-976a0415eab9"
            # 确保主机地址以http或https开头
            if not host.startswith(('http://', 'https://')):
                host = 'https://' + host

            # 发送请求
            response = requests.get(host, timeout=timeout)

            # 获取响应文本
            response_text = response.text

            # 如果需要，先进行base64解码
            if decode_base64:
                try:
                    response_text = base64.b64decode(response_text).decode('utf-8', errors='ignore')
                except Exception as e:
                    return f"❌ {host} - Base64解码错误: {str(e)}\n"

            # 计算搜索字符串出现次数
            matches = len(re.findall(re.escape(search_string), response_text))

            # 如果找到匹配项
            if matches > 0:
                return f"✅ {host} - 找到 {matches} 次匹配\n"
            return None

        except requests.RequestException as e:
            # 处理请求异常
            return f"❌ {host} - 错误: {str(e)}\n"

    def start_check(self):
        """开始多线程检测网站"""
        # 清空之前的结果
        self.result_text.delete('1.0', tk.END)

        # 获取主机地址和搜索字符串
        hosts = self.host_text.get('1.0', tk.END).strip().split('\n')
        search_string = self.search_entry.get().strip() or "{name:"

        # 获取线程数和超时时间
        max_threads = int(self.thread_var.get())
        timeout = int(self.timeout_var.get())
        decode_base64 = bool(self.decode_var.get())
        composite_check= bool(self.composite_check_var.get())

        # 移除空行
        hosts = [host.strip() for host in hosts if host.strip()]

        # 禁用开始按钮，防止重复点击
        self.start_check_button.config(state=tk.DISABLED)

        # 重置进度条
        self.progress['maximum'] = len(hosts)
        self.progress['value'] = 0

        # 更新状态标签
        start_time = time.time()
        self.status_label.config(text=f"正在检测 0/{len(hosts)} 个网站...")

        def update_progress():
            """更新进度和耗时"""
            completed = self.progress['value']
            current_time = time.time() - start_time
            self.status_label.config(text=f"已检测 {completed}/{len(hosts)} 个网站 | 耗时: {current_time:.2f}秒")
            self.master.update()

        def check_thread():
            """多线程检测的主函数"""
            # 使用线程池进行并发检测
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 提交所有任务
                future_to_host = {
                    executor.submit(self.check_website, host, search_string, timeout, decode_base64,composite_check): host
                    for host in hosts
                }

                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_host):
                    try:
                        result = future.result()
                        if result:
                            with self.result_lock:
                                self.result_text.insert(tk.END, result)
                                self.result_text.see(tk.END)

                        # 更新进度
                        self.progress['value'] += 1
                        update_progress()
                    except Exception as exc:
                        print(f'任务生成异常: {exc}')

            # 检测完成
            self.master.after(0, self.on_check_complete)

        # 启动检测线程
        threading.Thread(target=check_thread, daemon=True).start()

    def on_check_complete(self):
        """检测完成后的处理"""
        self.start_check_button.config(state=tk.NORMAL)
        messagebox.showinfo("检测完成", "所有网站检测已完成！")

    def clear_results(self):
        """清空无效结果"""
        # 获取当前结果文本
        result_text = self.result_text.get('1.0', tk.END)

        # 使用正则表达式删除以 "❌" 开头的行
        cleared_text = '\n'.join([line for line in result_text.split('\n') if not line.startswith('❌')])

        # 更新结果文本框
        self.result_text.delete('1.0', tk.END)
        self.result_text.insert(tk.END, cleared_text)


def main():
    root = tk.Tk()
    app = WebsiteChecker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
