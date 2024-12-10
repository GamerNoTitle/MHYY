import httpx
import json
import os
import re
import sentry_sdk
import random
import time
import yaml
import logging

# 配置 Sentry
sentry_sdk.init(
    "https://425d7b4536f94c9fa540fe34dd6609a2@o361988.ingest.sentry.io/6352584",
    traces_sample_rate=1.0,
)

# 配置日志级别
loglevel_env = os.environ.get("MHYY_LOGLEVEL", "INFO").upper()
loglevel = getattr(logging, loglevel_env, logging.INFO)

# 配置日志
logging.basicConfig(
    level=loglevel,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger()

# 配置数据写入脚本
config_datas = """
accounts:
  - token: your_token_here
    type: 2
    sysver: your_sysver
    deviceid: your_deviceid
    devicename: your_devicename
    devicemodel: your_devicemodel
    appid: 1953439974
    region: cn
"""

class RunError(Exception):
    pass

def handler(*args):
    """
    云函数入口函数。
    """
    # 读取配置
    conf_data = yaml.load(config_datas, Loader=yaml.FullLoader)
    if not conf_data or "accounts" not in conf_data:
        logger.error("请正确配置账户信息后再运行本脚本！")
        return {"statusCode": 1, "message": "配置错误，请检查账户信息。"}

    conf = conf_data["accounts"]
    if not conf:
        logger.error("账户配置为空！")
        return {"statusCode": 1, "message": "账户配置为空，请添加账户信息。"}

    logger.info(f"检测到 {len(conf)} 个账号，正在进行任务……")

    # 获取 SCT 通知配置
    sct_status = os.environ.get("sct")  # https://sct.ftqq.com/
    sct_key = os.environ.get("sct_key")
    sct_url = f"https://sctapi.ftqq.com/{sct_key}.send?title=MHYY-AutoCheckin 自动推送" if sct_key else None

    sct_msg = ""

    try:
        # 随机等待时间以避免被封禁
        debug_mode = os.environ.get("MHYY_DEBUG", "False").upper() == "TRUE"
        if not debug_mode:
            wait_time = random.randint(10, 60)
            logger.info(f"为了避免同一时间签到人数太多导致被官方怀疑，开始休眠 {wait_time} 秒")
            time.sleep(wait_time)

        # 获取最新版本号
        try:
            ver_info = httpx.get(
                "https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?game_ids[]=1Z8W5NHUQb&launcher_id=jGHBHlcOq1",
                timeout=60,
                verify=False,
            ).text
            version = json.loads(ver_info)["data"]["game_branches"][0]["main"]["tag"]
            logger.info(f"从官方API获取到云·原神最新版本号：{version}")
        except Exception as e:
            version = "5.0.0"
            logger.warning(f"获取版本号失败，使用默认版本：{version}")

        # 遍历每个账户进行任务
        for idx, config in enumerate(conf, start=1):
            if not config:
                raise RunError("账户配置为空，请添加账户信息。")

            # 提取账户配置
            token = config.get("token")
            client_type = config.get("type")
            sysver = config.get("sysver")
            deviceid = config.get("deviceid")
            devicename = config.get("devicename")
            devicemodel = config.get("devicemodel")
            appid = config.get("appid")
            region = config.get("region", "cn")

            if not all([token, client_type, sysver, deviceid, devicename, devicemodel, appid]):
                logger.error(f"第 {idx} 个账户配置不完整，请检查配置。")
                sct_msg += f"第 {idx} 个账户配置不完整，请检查配置。\n"
                continue

            # 构建请求头
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
            }

            # 处理国际服
            if region == "os":
                headers.update({
                    "x-rpc-channel": "mihoyo",
                    "x-rpc-cg_game_biz": "hk4e_global",
                    "x-rpc-op_biz": "clgm_global",
                    "x-rpc-cg_game_id": "9000254",
                    "x-rpc-app_id": "600493",
                    "User-Agent": "okhttp/4.10.0",
                    "Host": "sg-cg-api.hoyoverse.com",
                })
                NotificationURL = "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
                WalletURL = "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/wallet/wallet/get"
                AnnouncementURL = "https://sg-cg-api.hoyoverse.com/hk4e_global/cg/gamer/api/getAnnouncementInfo"
            else:
                NotificationURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
                WalletURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/wallet/wallet/get"
                AnnouncementURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/getAnnouncementInfo"

            logger.info(f"正在进行第 {idx} 个账号，服务器为{'GLOBAL' if region == 'os' else 'CN'}……")

            try:
                # 获取钱包信息
                wallet_response = httpx.get(WalletURL, headers=headers, timeout=60, verify=False)
                wallet_data = wallet_response.json()
                logger.debug(wallet_data)

                if wallet_data == {
                    "data": None,
                    "message": "登录已失效，请重新登录",
                    "retcode": -100,
                }:
                    logger.error(f"账号 {idx} 登录已过期，请重新登陆！返回为：{wallet_response.text}")
                    sct_msg += f"账号 {idx} 登录已过期，请重新登陆！返回为：{wallet_response.text}\n"
                    continue
                else:
                    free_time = wallet_data['data']['free_time']['free_time']
                    play_card_status = wallet_data['data']['play_card']['short_msg']
                    coin_num = wallet_data['data']['coin']['coin_num']
                    logger.info(
                        f"账号 {idx}: 你当前拥有免费时长 {free_time} 分钟，畅玩卡状态为 {play_card_status}，拥有原点 {coin_num} 点（{int(coin_num)/10}分钟）"
                    )
                    sct_msg += (
                        f"账号 {idx}: 你当前拥有免费时长 {free_time} 分钟，"
                        f"畅玩卡状态为 {play_card_status}，拥有原点 {coin_num} 点（{int(coin_num)/10}分钟）\n"
                    )

                # 获取公告信息
                announcement_response = httpx.get(AnnouncementURL, headers=headers, timeout=60, verify=False)
                announcement_data = announcement_response.json()
                logger.debug(f'获取到公告列表：{announcement_data["data"]}')

                # 获取签到通知
                notification_response = httpx.get(NotificationURL, headers=headers, timeout=60, verify=False)
                notification_data = notification_response.json()
                logger.debug(notification_data)

                # 解析签到状态
                success, Signed, Over = False, False, False
                try:
                    notifications = notification_data["data"]["list"]
                    if not notifications:
                        success = True
                        Signed = True
                        Over = False
                    else:
                        last_msg = json.loads(notifications[-1]["msg"])
                        if last_msg.get("msg") == "每日登录奖励":
                            success = True
                            Signed = False
                            Over = False
                        elif last_msg.get("over_num", 0) > 0:
                            success = True
                            Signed = False
                            Over = True
                        else:
                            success = False
                except (IndexError, json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"解析签到状态时出错: {e}")
                    success = False

                if success:
                    if Signed:
                        logger.info(f"账号 {idx}: 获取签到情况成功！今天是否已经签到过了呢？")
                        sct_msg += f"账号 {idx}: 获取签到情况成功！今天是否已经签到过了呢？\n"
                        logger.debug(f"完整返回体为：{notification_response.text}")
                    elif not Signed and Over:
                        last_msg = json.loads(notifications[-1]["msg"])
                        logger.info(
                            f"账号 {idx}: 获取签到情况成功！当前免费时长已经达到上限！签到情况为{last_msg}"
                        )
                        sct_msg += (
                            f"账号 {idx}: 获取签到情况成功！当前免费时长已经达到上限！签到情况为{last_msg}\n"
                        )
                    else:
                        logger.info(f"账号 {idx}: 已经签到过了！")
                        sct_msg += f"账号 {idx}: 已经签到过了！\n"
                else:
                    logger.info(f"账号 {idx}: 当前没有签到！请稍后再试！")
                    sct_msg += f"账号 {idx}: 当前没有签到！请稍后再试！\n"

                # 发送 SCT 通知
                if sct_url:
                    try:
                        sct_response = httpx.get(sct_url, params={"desp": sct_msg}, timeout=30)
                        if sct_response.status_code == 200:
                            logger.info("SCT 推送完成！")
                        else:
                            logger.warning(f"SCT 无法推送，状态码：{sct_response.status_code}, 响应：{sct_response.text}")
                    except Exception as e:
                        logger.error(f"SCT 推送时出错：{e}")

            except Exception as e:
                logger.error(f"账号 {idx} 执行过程中出错：{str(e)}")
                sct_msg += f"账号 {idx} 执行过程中出错：{str(e)}\n"
                if sct_url:
                    try:
                        httpx.get(sct_url, params={"desp": sct_msg}, timeout=30)
                    except Exception as notify_error:
                        logger.error(f"SCT 推送时出错：{notify_error}")
                continue

        logger.info("所有任务已经执行完毕！")
        return {"statusCode": 0, "message": "所有任务已经执行完毕！", "details": sct_msg}

    except RunError as re:
        logger.error(f"运行错误：{str(re)}")
        if sct_url:
            try:
                httpx.get(sct_url, params={"desp": f"运行错误：{str(re)}"}, timeout=30)
            except Exception as notify_error:
                logger.error(f"SCT 推送时出错：{notify_error}")
        return {"statusCode": 1, "message": f"运行错误：{str(re)}"}

    except Exception as e:
        logger.error(f"未知错误：{str(e)}")
        if sct_url:
            try:
                httpx.get(sct_url, params={"desp": f"未知错误：{str(e)}"}, timeout=30)
            except Exception as notify_error:
                logger.error(f"SCT 推送时出错：{notify_error}")
        return {"statusCode": 1, "message": f"未知错误：{str(e)}"}
