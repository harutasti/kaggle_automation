import logging
import sys

def setup_logger(log_file='app.log', level=logging.INFO):
    """ロガーを設定する関数"""
    logger = logging.getLogger('AutoKaggle')
    logger.setLevel(level)
    logger.handlers.clear() # ハンドラが重複しないようにクリア

    # ファイルハンドラの設定
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(level)

    # コンソールハンドラの設定
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)

    # フォーマッタの設定
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    detailed_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    fh.setFormatter(detailed_formatter)
    ch.setFormatter(formatter)

    # ハンドラをロガーに追加
    logger.addHandler(fh)
    logger.addHandler(ch)

    # 他のライブラリのログレベルを調整（任意）
    logging.getLogger('git').setLevel(logging.WARNING)

    return logger

# グローバルロガーインスタンス（必要に応じて）
# logger = setup_logger()
