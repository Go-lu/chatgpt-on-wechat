import os
import time

import nonebot
from nonebot.adapters.onebot.v11 import Adapter, Bot
from pathlib import Path

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel
from common.singleton import singleton
from common.utils import split_string_by_utf8_length
from config import conf
from common.log import logger
from voice.audio_convert import any_to_amr, split_audio

import asyncio

MAX_UTF8_LEN = 2048


@singleton
class NoneBotChannel(ChatChannel):
    NOT_SUPPORT_REPLYTYPE = []
    """
    NoneBot消息通道
    """

    def __init__(self):
        super().__init__()
        self.Driver = conf().get("nonebot_driver", "~websockets")  # nonebot驱动
        self.HOST = conf().get("nonebot_listen_host", "127.0.0.1")  # nonebot监听地址
        self.PORT = conf().get("nonebot_listen_port", "1314")  # nonebot监听端口
        self.ACCESS_TOKEN = conf().get("nonebot_access_token")  # nonebot访问令牌
        self.SuperUsers = conf().get("nonebot_superusers", [])  # nonebot超级用户
        self.NickName = conf().get("nonebot_nickname", ["Bot"])  # nonebot昵称
        self.CommandStart = conf().get("nonebot_command_start", ["/"])  # nonebot命令前缀
        self.CommandSep = conf().get("nonebot_command_sep", [" "])  # nonebot命令分隔符

        logger.info(
            "[nonebot] init: driver: {}, host: {}, port: {}, access_token: {}, superusers: {}, nickname: {}, "
            "command_start: {}, command_sep: {}".format(self.Driver, self.HOST, self.PORT, self.ACCESS_TOKEN,
                                                        self.SuperUsers, self.NickName, self.CommandStart,
                                                        self.CommandSep))

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        bot: Bot = context['msg'].bot

        is_group = context["msg"].is_group

        if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:
            reply_text = reply.content
            texts = split_string_by_utf8_length(reply_text, MAX_UTF8_LEN)
            if len(texts) > 1:
                logger.info("[NoneBot] text too long, split into {} parts".format(len(texts)))
            for i, text in enumerate(texts):
                # 发送文本消息
                try:
                    asyncio.run(bot.send_msg(
                        message_type="group" if is_group else "private",
                        user_id=context["msg"].from_user_id,
                        group_id=receiver if is_group else None,
                        message=text
                    ))
                except Exception as e:
                    logger.error(f"[NoneBot] send message failed: {e}")
                    return
                if i != len(texts) - 1:
                    time.sleep(0.5)  # 休眠0.5秒，防止发送过快乱序
            logger.info("[NoneBot] send message to {}: {}".format(context["msg"].from_user_nickname, reply_text))
        elif reply.type == ReplyType.VOICE:
            try:
                media_ids = []
                file_path = reply.content
                amr_file = os.path.splitext(file_path)[0] + ".amr"
                any_to_amr(file_path, amr_file)
                duration, files = split_audio(amr_file, 60 * 1000)
                if len(files) > 1:
                    logger.info(
                        "[NoneBot] voice too long, {}s > 60s, split into {} parts".format(duration / 1000.0, len(files))
                    )
                for path in files:
                    # 发送消息 voice
                    try:
                        asyncio.run(bot.send_msg(
                            message_type="group" if is_group else "private",
                            user_id=context["msg"].from_user_id,
                            group_id=receiver if is_group else None,
                            message="[CQ:record,file=file:///{}]".format(path),
                            auto_escape=False
                        ))
                    except Exception as e:
                        logger.error(f"[NoneBot] upload voice failed: {e}")
                        return
                    time.sleep(1)
            except Exception as e:
                logger.error(f"[NoneBot] send voice failed: {e}")
                return
            try:
                os.remove(file_path)
                if amr_file != file_path:
                    os.remove(amr_file)
            except Exception as e:
                logger.error(f"[NoneBot] remove voice file failed: {e}")
            logger.info(f"[NoneBot] send voice to {context['msg'].from_user_nickname}: {reply.content}")
        elif reply.type == ReplyType.IMAGE_URL:
            img_url = reply.content
            try:
                # 发送图片
                asyncio.run(bot.send_msg(
                    message_type="group" if is_group else "private",
                    user_id=context["msg"].from_user_id,
                    group_id=receiver if is_group else None,
                    message="[CQ:image,file={}]".format(img_url),
                    auto_escape=False
                ))
            except Exception as e:
                logger.error(f"[NoneBot] send image failed: {e}")
                return
            logger.info(f"[NoneBot] send image to {context['msg'].from_user_nickname}: {reply.content}")
        elif reply.type == ReplyType.IMAGE:  # 本地图片
            image_storage = reply.content
            if type(image_storage) != str:
                logger.warning("非本地路径图片暂不支持处理，联系开发者适配或自己完善此方法~")
                return
            try:
                # 发送本地图片
                asyncio.run(bot.send_msg(
                    message_type="group" if is_group else "private",
                    user_id=context["msg"].from_user_id,
                    group_id=receiver if is_group else None,
                    message="[CQ:image,file=file:///{}]".format(image_storage),
                    auto_escape=False
                ))
            except Exception as e:
                logger.error(f"[NoneBot] send image failed: {e}")
                return
            logger.info(f"[NoneBot] send image to {context['msg'].from_user_nickname}: {reply.content}")

    def startup(self):
        # 启动nonebot
        nonebot.init(
            driver=self.Driver,
            host=self.HOST,
            port=self.PORT,
            onebot_access_token=self.ACCESS_TOKEN,
            superusers=set(self.SuperUsers),
            nickname=set(self.NickName),
            command_start=set(self.CommandStart),
            command_sep=set(self.CommandSep)
        )

        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)

        # 获取当前运行目录
        # print("=============")
        pyprojectPath = Path(__file__).parent / "pyproject.toml"
        print(pyprojectPath)

        # 加载插件
        # nonebot.load_builtin_plugin("echo")  # 内置插件，用以测试
        nonebot.load_from_toml(str(pyprojectPath), encoding="utf-8")
        # nonebot.load_plugin("none_bot/plugins/chatWithAI/__init__.py")  # 本地插件

        nonebot.run()  # 运行bot
