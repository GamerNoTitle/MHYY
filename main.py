import httpx
import json
import os
import re
import sentry_sdk
import random
import time
import yaml
import logging

if os.environ.get("MHYY_LOGLEVEL", "").upper() == "DEBUG":
    loglevel = logging.DEBUG
elif os.environ.get("MHYY_LOGLEVEL", "").upper() == "WARNING":
    loglevel = logging.WARNING
elif os.environ.get("MHYY_LOGLEVEL", "").upper() == "ERROR":
    loglevel = logging.ERROR
else:
    loglevel = logging.INFO

# 设置日志配置
logging.basicConfig(
    level=loglevel,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger()


def ReadConf(variable_name, default_value=None):
    # Try to get the variable from the environment
    env_value = os.environ.get(variable_name)

    if env_value:
        config_data = yaml.load(env_value, Loader=yaml.FullLoader)
        return config_data

    # If not found in environment, try to read from config.yml
    try:
        with open("config.yml", "r", encoding="utf-8") as config_file:
            config_data = yaml.load(config_file, Loader=yaml.FullLoader)
            return config_data
    except FileNotFoundError:
        return default_value


sentry_sdk.init(
    "https://425d7b4536f94c9fa540fe34dd6609a2@o361988.ingest.sentry.io/6352584",
    traces_sample_rate=1.0,
)

conf = ReadConf("MHYY_CONFIG")["accounts"]

if not conf:
    logger.error("请正确配置环境变量或者config.yml后再运行本脚本！")
    os._exit(0)
logger.info(f"检测到 {len(conf)} 个账号，正在进行任务……")


# Options
sct_status = os.environ.get("sct")  # https://sct.ftqq.com/
sct_key = os.environ.get("sct_key")
sct_url = f"https://sctapi.ftqq.com/{sct_key}.send?title=MHYY-AutoCheckin 自动推送"

sct_msg = ""


class RunError(Exception):
    pass


if __name__ == "__main__":
    if not os.environ.get("MHYY_DEBUG", False):
        wait_time = random.randint(10, 60)  # Random Sleep to Avoid Ban
        logger.info(f"为了避免同一时间签到人数太多导致被官方怀疑，开始休眠 {wait_time} 秒")
        time.sleep(wait_time)
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

    for config in conf:
        # 各种API的URL
        NotificationURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
        WalletURL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/wallet/wallet/get"
        AnnouncementURL = (
            "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/getAnnouncementInfo"
        )

        if config == "":
            # Verify config
            raise RunError(
                f"请在Settings->Secrets->Actions页面中新建名为config的变量，并将你的配置填入后再运行！"
            )
        else:
            token = config["token"]
            client_type = config["type"]
            sysver = config["sysver"]
            deviceid = config["deviceid"]
            devicename = config["devicename"]
            devicemodel = config["devicemodel"]
            appid = config["appid"]
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
        bbsid = re.findall(r"oi=[0-9]+", token)[0].replace("oi=", "")
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
            f"正在进行第 {conf.index(config) + 1} 个账号，服务器为{'CN' if region != 'os' else 'GLOBAL'}……"
        )
        try:
            wallet = httpx.get(WalletURL, headers=headers, timeout=60, verify=False)
            logger.debug(wallet.text)
            if json.loads(wallet.text) == {
                "data": None,
                "message": "登录已失效，请重新登录",
                "retcode": -100,
            }:
                logger.error(f"当前登录已过期，请重新登陆！返回为：{wallet.text}")
                sct_msg += f"当前登录已过期，请重新登陆！返回为：{wallet.text}"
            else:
                logger.info(
                    f"你当前拥有免费时长 {json.loads(wallet.text)['data']['free_time']['free_time']} 分钟，畅玩卡状态为 {json.loads(wallet.text)['data']['play_card']['short_msg']}，拥有原点 {json.loads(wallet.text)['data']['coin']['coin_num']} 点（{int(json.loads(wallet.text)['data']['coin']['coin_num'])/10}分钟）"
                )
                sct_msg += f"你当前拥有免费时长 {json.loads(wallet.text)['data']['free_time']['free_time']} 分钟，畅玩卡状态为 {json.loads(wallet.text)['data']['play_card']['short_msg']}，拥有原点 {json.loads(wallet.text)['data']['coin']['coin_num']} 点（{int(json.loads(wallet.text)['data']['coin']['coin_num'])/10}分钟）"
                announcement = httpx.get(
                    AnnouncementURL, headers=headers, timeout=60, verify=False
                )
                logger.debug(f'获取到公告列表：{json.loads(announcement.text)["data"]}')
                res = httpx.get(
                    NotificationURL, headers=headers, timeout=60, verify=False
                )
                success, Signed = False, False
                logger.debug(res.text)
                try:
                    if list(json.loads(res.text)["data"]["list"]) == []:
                        success = True
                        Signed = True
                        Over = False
                    elif (
                        json.loads(json.loads(res.text)["data"]["list"][-1]["msg"])[
                            "msg"
                        ]
                        == "每日登录奖励"
                    ):
                        success = True
                        Signed = False
                        Over = False
                    elif (
                        json.loads(json.loads(res.text)["data"]["list"][-1]["msg"])[
                            "over_num"
                        ]
                        > 0
                    ):
                        success = True
                        Signed = False
                        Over = True
                    else:
                        success = False
                except IndexError:
                    success = False
                if success:
                    if Signed:
                        logger.info(f"获取签到情况成功！今天是否已经签到过了呢？")
                        sct_msg += f"获取签到情况成功！今天是否已经签到过了呢？"
                        logger.debug(f"完整返回体为：{res.text}")
                    elif not Signed and Over:
                        logger.info(
                            f'获取签到情况成功！当前免费时长已经达到上限！签到情况为{json.loads(res.text)["data"]["list"][0]["msg"]}'
                        )
                        sct_msg += f"获取签到情况成功！当前免费时长已经达到上限！签到情况为{json.loads(res.text)['data']['list'][0]['msg']}"
                    else:
                        logger.info(f"已经签到过了！")
                        sct_msg += f"已经签到过了！"
                else:
                    logger.info(f"当前没有签到！请稍后再试！")
                    sct_msg += f"当前没有签到！请稍后再试！"
                if sct_key:
                    httpx.get(sct_url, params={"desp": sct_msg})
        except Exception as e:
            logger.error(f"执行过程中出错：{str(e)}")
            sct_msg += f"执行过程中出错：{str(e)}"
            if sct_key:
                httpx.get(sct_url, params={"desp": sct_msg})
            raise RunError(str(e))
    logger.info("所有任务已经执行完毕！")
