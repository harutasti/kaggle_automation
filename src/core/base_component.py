import logging

class BaseComponent:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(f'AutoKaggle.{self.__class__.__name__}')
        self.logger.info(f"Initialized {self.__class__.__name__}")

    def _log_start(self, method_name: str, **kwargs):
        self.logger.info(f"Starting {method_name}...")
        if kwargs:
            self.logger.debug(f"Input args: {kwargs}")

    def _log_end(self, method_name: str, result: any = None):
        self.logger.info(f"Finished {method_name}.")
        if result is not None:
             # 大きすぎる結果はログに出さないように調整が必要な場合も
            try:
                result_repr = repr(result)
                if len(result_repr) > 500: # 例: 500文字以上の結果は省略
                   result_repr = result_repr[:500] + "..."
                self.logger.debug(f"Output: {result_repr}")
            except Exception:
                 self.logger.debug("Output: [Could not represent result for logging]")

    def _log_error(self, method_name: str, error: Exception):
        self.logger.error(f"Error in {method_name}: {error}", exc_info=True)
