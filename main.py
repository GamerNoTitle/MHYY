import httpx
import json
import os
import re
import sentry_sdk
import random
import time
import yaml
import logging

# --- Logging Setup ---
if os.environ.get("MHYY_LOGLEVEL", "").upper() == "DEBUG":
    loglevel = logging.DEBUG
elif os.environ.get("MHYY_LOGLEVEL", "").upper() == "WARNING":
    loglevel = logging.WARNING
elif os.environ.get("MHYY_LOGLEVEL", "").upper() == "ERROR":
    loglevel = logging.ERROR
else:
    loglevel = logging.INFO

logging.basicConfig(
    level=loglevel,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger()


# --- Config Reading Function ---
def ReadConf(variable_name, default_value=None):
    """
    Reads YAML configuration from environment variable or config.yml.
    Assumes the variable_name contains the full YAML content.
    """
    env_value = os.environ.get(variable_name)

    if env_value:
        try:
            # Attempt to load from environment variable (assuming it's YAML)
            config_data = yaml.load(env_value, Loader=yaml.FullLoader)
            logger.debug("Configuration loaded from environment variable.")
            return config_data
        except yaml.YAMLError as e:
            logger.error(
                f"Failed to parse YAML from environment variable '{variable_name}': {e}"
            )
            return default_value  # Return default or None if env parsing fails
        except Exception as e:
            logger.error(
                f"An unexpected error occurred reading environment variable '{variable_name}': {e}"
            )
            return default_value

    # If not found or failed in environment, try to read from config.yml
    try:
        with open("config.yml", "r", encoding="utf-8") as config_file:
            config_data = yaml.load(config_file, Loader=yaml.FullLoader)
            logger.debug("Configuration loaded from config.yml file.")
            return config_data
    except FileNotFoundError:
        logger.warning("config.yml not found.")
        return default_value
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML from config.yml: {e}")
        return default_value
    except Exception as e:
        logger.error(f"An unexpected error occurred reading config.yml: {e}")
        return default_value


# --- Sentry Setup ---
sentry_sdk.init(
    "https://425d7b4536f94c9fa540fe34dd6609a2@o361988.ingest.sentry.io/6352584",
    traces_sample_rate=1.0,
)

# --- Load Configuration ---
full_config = ReadConf("MHYY_CONFIG", {})  # Read the entire config
accounts_conf = full_config.get("accounts")
notification_settings = full_config.get(
    "notifications", {}
)  # Get notification settings, default to empty dict
proxy_settings = full_config.get("proxy")

if proxy_settings:
    logger.info(f"检测到代理设置: {proxy_settings}")

if not accounts_conf:
    logger.error(
        "请正确配置环境变量 MHYY_CONFIG 或者 config.yml 并包含 'accounts' 部分后再运行本脚本！"
    )
    os._exit(0)
logger.info(f"检测到 {len(accounts_conf)} 个账号，正在进行任务……")


def send_notifications(message: str, settings: dict, proxy: str = None):
    """Sends message to configured notification services."""
    if not message or not settings:
        logger.debug("No message to send or no notification settings configured.")
        return

    logger.info("Attempting to send notifications...")

    # ServerChan (SCT)
    sct_conf = settings.get("serverchan", {})
    sct_key = sct_conf.get("key")
    if sct_key:
        sct_url = f"https://sctapi.ftqq.com/{sct_key}.send"
        try:
            payload = {"title": "MHYY-AutoCheckin 状态推送", "desp": message}
            response = httpx.get(sct_url, params=payload, timeout=10)
            response.raise_for_status()
            logger.info("ServerChan notification sent successfully.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"ServerChan HTTP error occurred: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting ServerChan: {e}")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred sending ServerChan notification: {e}"
            )
    else:
        logger.debug("ServerChan not configured.")

    # DingTalk
    dingtalk_conf = settings.get("dingtalk", {})
    dingtalk_webhook_url = dingtalk_conf.get("webhook_url")
    if dingtalk_webhook_url:
        try:
            payload = {"msgtype": "text", "text": {"content": message}}
            response = httpx.post(dingtalk_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("DingTalk notification sent successfully.")
            else:
                logger.error(
                    f"DingTalk error: {result.get('errcode')} - {result.get('errmsg')}"
                )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"DingTalk HTTP error occurred: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting DingTalk: {e}")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred sending DingTalk notification: {e}"
            )
    else:
        logger.debug("DingTalk not configured.")

    # PushPlus
    sct_conf = settings.get("pushplus", {})
    sct_key = sct_conf.get("key")
    if sct_key:
        sct_url = f"http://www.pushplus.plus/send/{sct_key}"
        try:
            payload = {"title": "MHYY-AutoCheckin 状态推送", "content": message}
            response = httpx.post(sct_url, data=payload, timeout=10)
            response.raise_for_status()
            logger.info("PushPlus notification sent successfully.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"PushPlus HTTP error occurred: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting PushPlus: {e}")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred sending PushPlus notification: {e}"
            )
    else:
        logger.debug("PushPlus not configured.")


    # Telegram
    telegram_conf = settings.get("telegram", {})
    telegram_bot_token = telegram_conf.get("bot_token")
    telegram_chat_id = telegram_conf.get("chat_id")
    if telegram_bot_token and telegram_chat_id:
        telegram_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        try:
            # Telegram text message parameters
            params = {
                "chat_id": telegram_chat_id,
                "text": message,
                # Optional: parse_mode can be 'MarkdownV2', 'HTML', or None
                # For simplicity, sending as plain text. Be careful with special characters if using Markdown/HTML.
                # "parse_mode": "HTML"
            }
            logger.info("Sending Telegram notification...")
            logger.debug(f"Proxy settings: {proxy}")
            response = httpx.get(telegram_url, params=params, timeout=10, proxy=proxy)
            response.raise_for_status()  # Raise an exception for bad status codes
            result = response.json()
            logger.info(f"Telegram response: {result}")
            if result.get("ok"):
                logger.info("Telegram notification sent successfully.")
            else:
                logger.error(
                    f"Telegram error: {result.get('error_code')} - {result.get('description')}"
                )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Telegram HTTP error occurred: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting Telegram: {e}")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred sending Telegram notification: {e}"
            )
    else:
        logger.debug("Telegram not configured.")


class RunError(Exception):
    pass


if __name__ == "__main__":
    if not os.environ.get("MHYY_DEBUG", False):
        wait_time = random.randint(1, 2)  # Random Sleep to Avoid Ban
        logger.info(
            f"为了避免同一时间签到人数太多导致被官方怀疑，开始休眠 {wait_time} 秒"
        )
        time.sleep(wait_time)

    version = "5.0.0"  # Default version
    try:
        ver_info = httpx.get(
            "https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?game_ids[]=1Z8W5NHUQb&launcher_id=jGHBHlcOq1",
            timeout=60,
            verify=False,
        ).text
        version = json.loads(ver_info)["data"]["game_branches"][0]["main"]["tag"]
        logger.info(f"从官方API获取到云·原神最新版本号：{version}")
    except Exception as e:
        logger.warning(f"获取版本号失败，使用默认版本：{version}. Error: {e}")

    for config in accounts_conf:
        notification_msg = (
            "【MHYY】签到状态推送\n\n"  # Message container for the current account
        )

        # 各种API的URL
        NotificationURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
        WalletURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/wallet/wallet/get"
        AnnouncementURL = (
            "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/getAnnouncementInfo"
        )

        # Validate account config entry
        if not isinstance(config, dict) or "token" not in config:
            error_msg = f"跳过无效的账号配置条目: {config}"
            logger.error(error_msg)
            notification_msg += error_msg + "\n"
            send_notifications(
                notification_msg, notification_settings, proxy=proxy_settings if proxy_settings else None
            )  # Notify about invalid config
            continue  # Skip this entry

        try:
            token = config["token"]
            client_type = config.get("type", 5)
            sysver = config.get("sysver", "14.0")
            deviceid = config["deviceid"]
            devicename = config.get("devicename", "iPhone 13")
            devicemodel = config.get("devicemodel", "iPhone13,3")
            appid = config.get("appid", "1953439978")

            # Construct headers
            headers = {
                "x-rpc-combo_token": token,
                "x-rpc-client_type": str(client_type),
                "x-rpc-app_version": str(version),
                "x-rpc-sys_version": str(sysver),
                "x-rpc-channel": "cyydmihoyo",
                "x-rpc-device_id": deviceid,
                "x-rpc-device_name": devicename,
                "x-rpc-device_model": devicemodel,
                "x-rpc-vendor_id": "1",
                "x-rpc-cg_game_biz": "hk4e_cn",
                "x-rpc-op_biz": "clgm_cn",
                "x-rpc-language": "zh-cn",
                "Host": "api-cloudgame.mihoyo.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip",
                "User-Agent": f"Mozilla/5.0 (iPhone; CPU iPhone OS {sysver} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            }

            bbsid_match = re.search(r"oi=(\d+)", token)
            bbsid = bbsid_match.group(1) if bbsid_match else "N/A"

            region = config.get("region", "cn")
            if region == "os":
                headers["x-rpc-channel"] = "mihoyo"
                headers["x-rpc-cg_game_biz"] = "hk4e_global"
                headers["x-rpc-op_biz"] = "clgm_global"
                headers["x-rpc-cg_game_id"] = "9000254"
                headers["x-rpc-app_id"] = "600493"
                headers["User-Agent"] = "okhttp/4.10.0"
                headers["Host"] = "sg-cg-api.hoyoverse.com"
                NotificationURL = "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
                WalletURL = (
                    "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/wallet/wallet/get"
                )
                AnnouncementURL = "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/gamer/api/getAnnouncementInfo"

            logger.info(
                f"--- 正在进行第 {accounts_conf.index(config) + 1} 个账号 (BBSID: {bbsid})，服务器为{'CN' if region != 'os' else 'GLOBAL'} ---"
            )
            notification_msg += (
                f"☁️ 云原神签到结果 ({'CN' if region != 'os' else 'GLOBAL'}):\n"
            )
            notification_msg += (
                f"账号 {accounts_conf.index(config) + 1} (BBSID: {bbsid})\n\n"
            )

            try:
                wallet_res = httpx.get(
                    WalletURL, headers=headers, timeout=30, verify=False
                )
                wallet_res.raise_for_status()
                wallet_data = wallet_res.json()
                logger.debug(f"Wallet response: {wallet_data}")

                if wallet_data.get("retcode") == -100:
                    error_msg = f"当前登录已过期，请重新登陆！返回为：{wallet_data.get('message', 'Unknown error')}"
                    logger.error(error_msg)
                    notification_msg += error_msg + "\n"
                elif wallet_data.get("retcode") == 0 and wallet_data.get("data"):
                    free_time = wallet_data["data"]["free_time"]["free_time"]
                    play_card_msg = wallet_data["data"]["play_card"]["short_msg"]
                    coin_num = wallet_data["data"]["coin"]["coin_num"]
                    coin_minutes = int(coin_num) / 10 if coin_num is not None else 0
                    wallet_status = f"✅ 钱包：免费时长 {free_time} 分钟，畅玩卡状态为「{play_card_msg}」，拥有原点 {coin_num} 点 ({coin_minutes:.0f}分钟)\n"
                    logger.info(wallet_status.strip())
                    notification_msg += wallet_status
                else:
                    error_msg = f"获取钱包信息失败: {wallet_data.get('retcode')} - {wallet_data.get('message', 'Unknown error')}"
                    logger.error(error_msg)
                    notification_msg += error_msg + "\n"

            except httpx.HTTPStatusError as e:
                error_msg = f"获取钱包信息HTTP错误: {e.response.status_code} - {e.response.text}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"
            except httpx.RequestError as e:
                error_msg = f"请求钱包信息失败: {e}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"
            except Exception as e:
                error_msg = f"解析钱包信息出错: {e}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"

            # --- Check Sign-in Status ---
            try:
                announcement_res = httpx.get(
                    AnnouncementURL, headers=headers, timeout=30, verify=False
                )
                announcement_res.raise_for_status()
                # logger.debug(f'Announcement response: {announcement_res.text}') # Too verbose usually

                notification_res = httpx.get(
                    NotificationURL, headers=headers, timeout=30, verify=False
                )
                notification_res.raise_for_status()
                notification_data = notification_res.json()
                logger.debug(f"Notification response: {notification_data}")

                sign_in_status = "❓ 未知签到状态"  # Default status

                if notification_data.get("retcode") == 0 and notification_data.get(
                    "data"
                ):
                    notification_list = notification_data["data"].get("list", [])

                    if not notification_list:
                        sign_in_status = "✅ 今天似乎已经签到过了！(通知列表为空)"
                        logger.info(sign_in_status)
                        notification_msg += sign_in_status + "\n"
                    else:
                        # Look for a notification indicating sign-in reward or limit reached
                        # The logic here was a bit fragile, let's try to be more robust
                        # Look for specific message patterns if possible, or just check the presence of notifications

                        last_notification_msg = notification_list[0].get("msg")
                        if len(notification_list) > 0:
                            last_notification_msg = notification_list[-1].get("msg")

                        try:
                            # Attempt to parse the 'msg' field which is often a JSON string itself
                            msg_payload = json.loads(last_notification_msg)
                            logger.debug(
                                f"Parsed last notification msg payload: {msg_payload}"
                            )

                            if msg_payload.get("msg") == "每日登录奖励" or msg_payload.get("msg") == "每日登陆奖励":
                                # This indicates a successful sign-in
                                sign_in_status = f"✅ 获取签到情况成功！{msg_payload.get('msg')}：获得 {msg_payload.get('num')} 分钟"
                                logger.info(sign_in_status)
                                notification_msg += sign_in_status + "\n"
                            elif msg_payload.get("over_num", 0) > 0:
                                sign_in_status = f"✅ 获取签到情况成功！免费时长已达上限，只能获得 {msg_payload.get('num')} 分钟 (超出 {msg_payload.get('over_num')} 分钟)"
                                logger.info(sign_in_status)
                                notification_msg += sign_in_status + "\n"
                            else:
                                sign_in_status = f"❓ 获取到其他通知，可能已经签到或状态未知: {last_notification_msg}"
                                logger.info(sign_in_status)
                                notification_msg += sign_in_status + "\n"

                        except json.JSONDecodeError:
                            # 'msg' is not a JSON string
                            sign_in_status = f"❓ 获取到非标准通知，可能已经签到或状态未知: {last_notification_msg}"
                            logger.info(sign_in_status)
                            notification_msg += sign_in_status + "\n"
                        except Exception as e:
                            # Other errors during parsing msg
                            sign_in_status = f"❌ 解析通知详情时出错: {e}. Raw msg: {last_notification_msg}"
                            logger.error(sign_in_status)
                            notification_msg += sign_in_status + "\n"

                elif notification_data.get("retcode") != 0:
                    error_msg = f"获取通知列表失败: {notification_data.get('retcode')} - {notification_data.get('message', 'Unknown error')}"
                    logger.error(error_msg)
                    notification_msg += error_msg + "\n"

            except httpx.HTTPStatusError as e:
                error_msg = f"获取通知列表HTTP错误: {e.response.status_code} - {e.response.text}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"
            except httpx.RequestError as e:
                error_msg = f"请求通知列表失败: {e}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"
            except Exception as e:
                error_msg = f"检查签到状态时出错: {e}"
                logger.error(error_msg)
                notification_msg += error_msg + "\n"

        except KeyError as e:
            # This catches missing required keys in account config
            error_msg = f"账号配置缺少必需的键: {e}"
            logger.error(error_msg)
            notification_msg += f"❌ 账号配置错误: {error_msg}\n"
        except Exception as e:
            # Catch any other unexpected errors during account processing
            error_msg = f"处理账号时发生未知错误: {e}"
            logger.error(error_msg)
            notification_msg += f"❌ 账号处理错误: {error_msg}\n"

        if accounts_conf.index(config) < len(accounts_conf) - 1:
            notification_msg += "\n---\n\n"

        send_notifications(notification_msg, notification_settings, proxy=proxy_settings if proxy_settings else None)

    logger.info("所有任务已经执行完毕！")
