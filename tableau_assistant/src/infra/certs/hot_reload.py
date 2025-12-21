"""
证书热更新器

监控证书文件变化并自动重新加载。
"""
import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class HotReloader:
    """
    证书热更新器
    
    监控证书文件变化，支持：
    - 文件系统事件监控
    - 防抖处理
    - 定期刷新（用于公司证书）
    
    使用示例:
        reloader = HotReloader(
            watch_paths=["certs/server.pem", "certs/server.key"],
            callback=on_cert_change
        )
        reloader.start()
    """
    
    def __init__(
        self,
        watch_paths: List[str],
        callback: Callable[[], bool],
        debounce_seconds: float = 2.0,
        refresh_callback: Optional[Callable[[], bool]] = None,
        refresh_interval: int = 0
    ):
        """
        初始化热更新器
        
        Args:
            watch_paths: 要监控的文件路径列表
            callback: 文件变化时的回调函数，返回 True 表示重载成功
            debounce_seconds: 防抖间隔（秒）
            refresh_callback: 定期刷新回调（用于公司证书）
            refresh_interval: 刷新间隔（秒），0 表示不刷新
        """
        self.watch_paths = [Path(p) for p in watch_paths]
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.refresh_callback = refresh_callback
        self.refresh_interval = refresh_interval
        
        self._running = False
        self._watch_thread: Optional[threading.Thread] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._last_change_time = 0.0
        self._pending_reload = False
        self._lock = threading.Lock()
        
        # 记录文件修改时间
        self._file_mtimes: dict = {}
    
    def start(self) -> None:
        """启动文件监控和定期刷新"""
        if self._running:
            return
        
        self._running = True
        
        # 初始化文件修改时间
        self._update_mtimes()
        
        # 启动文件监控线程
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="CertWatcher"
        )
        self._watch_thread.start()
        logger.info("证书文件监控已启动")
        
        # 启动定期刷新线程
        if self.refresh_interval > 0 and self.refresh_callback:
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop,
                daemon=True,
                name="CertRefresher"
            )
            self._refresh_thread.start()
            logger.info(f"证书定期刷新已启动，间隔: {self.refresh_interval}秒")
    
    def stop(self) -> None:
        """停止文件监控和定期刷新"""
        self._running = False
        
        if self._watch_thread:
            self._watch_thread.join(timeout=5)
            self._watch_thread = None
        
        if self._refresh_thread:
            self._refresh_thread.join(timeout=5)
            self._refresh_thread = None
        
        logger.info("证书热更新已停止")
    
    def _update_mtimes(self) -> None:
        """更新文件修改时间记录"""
        for path in self.watch_paths:
            if path.exists():
                self._file_mtimes[str(path)] = path.stat().st_mtime
    
    def _check_changes(self) -> bool:
        """检查文件是否有变化"""
        changed = False
        
        for path in self.watch_paths:
            path_str = str(path)
            
            if not path.exists():
                if path_str in self._file_mtimes:
                    # 文件被删除
                    del self._file_mtimes[path_str]
                    changed = True
                continue
            
            current_mtime = path.stat().st_mtime
            
            if path_str not in self._file_mtimes:
                # 新文件
                self._file_mtimes[path_str] = current_mtime
                changed = True
            elif current_mtime != self._file_mtimes[path_str]:
                # 文件被修改
                self._file_mtimes[path_str] = current_mtime
                changed = True
        
        return changed
    
    def _watch_loop(self) -> None:
        """文件监控循环"""
        while self._running:
            try:
                if self._check_changes():
                    self._schedule_reload()
                
                # 处理待处理的重载
                self._process_pending_reload()
                
            except Exception as e:
                logger.error(f"文件监控错误: {e}")
            
            time.sleep(1)  # 每秒检查一次
    
    def _schedule_reload(self) -> None:
        """调度重载（带防抖）"""
        with self._lock:
            self._last_change_time = time.time()
            self._pending_reload = True
        
        logger.debug("检测到证书文件变化，等待防抖...")
    
    def _process_pending_reload(self) -> None:
        """处理待处理的重载"""
        with self._lock:
            if not self._pending_reload:
                return
            
            # 检查防抖时间
            elapsed = time.time() - self._last_change_time
            if elapsed < self.debounce_seconds:
                return
            
            self._pending_reload = False
        
        # 执行重载
        logger.info("执行证书重载...")
        try:
            success = self.callback()
            if success:
                logger.info("证书重载成功")
            else:
                logger.warning("证书重载失败，保持原证书")
        except Exception as e:
            logger.error(f"证书重载异常: {e}")
    
    def _refresh_loop(self) -> None:
        """定期刷新循环"""
        while self._running:
            # 等待刷新间隔
            for _ in range(self.refresh_interval):
                if not self._running:
                    return
                time.sleep(1)
            
            if not self._running:
                return
            
            # 执行刷新
            logger.info("执行证书定期刷新...")
            try:
                if self.refresh_callback:
                    success = self.refresh_callback()
                    if success:
                        logger.info("证书刷新成功")
                    else:
                        logger.debug("证书无需更新")
            except Exception as e:
                logger.error(f"证书刷新异常: {e}")


__all__ = ["HotReloader"]
