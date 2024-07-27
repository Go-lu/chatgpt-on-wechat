from channel.nonebot.bean.nonebot_message import NoneBotMessage
from channel.nonebot.nonebot_channel import NoneBotChannel
from channel.nonebot.bean.nonebot_raw_message import NoneBotRawMessage
from nonebot.adapters.onebot.v11 import MessageEvent, Bot
from nonebot import on_message
from nonebot import logger
from nonebot.rule import to_me
import subprocess
import re
import os

message = on_message(rule=to_me(), priority=9999999)


@message.handle()
async def handle_message(bot: Bot, event: MessageEvent):
    channel = NoneBotChannel()
    msg_type = "text"  # 初始消息类型默认为TEXT
    msg_is_group = False  # 默认非群内消息
    session_list = []  # 获取到的session为 群组：group_groupId_senderId  私信：senderId
    msg = str(event.get_message()).strip()  # 原始信息 字符串类型
    channel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    save_file_path = os.path.join(channel_path, "file")

    """
    CQ码解析
    """
    cq_code_json = await parse_cq_code(msg)
    # 消息类型判断
    if cq_code_json is not None:
        # msg_type = "voice" if cq_code_json["CQ"] == "record" else "image" if cq_code_json["CQ"] == "image" else "file"
        if cq_code_json["CQ"] == "record":
            msg_type = "voice"
            file_dict = await bot.get_record(file=cq_code_json["file"], out_format="amr")
            input_file = file_dict["file"]
            output_file = os.path.join(save_file_path, f"{cq_code_json['file'].split('.')[0]}.mp3")
            # 将语音 amr文件转为mp3文件
            await convert_silk_to_mp3(input_file, output_file)
            msg = output_file
        elif cq_code_json["CQ"] == "image":
            msg_type = "image"
            file_dict = await bot.get_image(file=cq_code_json['file'])
            msg = file_dict["file"]
        elif cq_code_json["CQ"] == "file":
            msg_type = "file"
            file_dict = await bot.get_image(file=cq_code_json['file'])  # 没有get_file api，用get_image顶一下
            msg = file_dict["file"]
    else:
        if msg.find("[CQ:") != -1:
            return

    msg_session_id = event.get_session_id()

    if msg_session_id.find("group") != -1:
        msg_is_group = True
        session_list = msg_session_id.split("_")

    # 构建原始数据对象
    nonebot_raw_msg = NoneBotRawMessage(
        msg_id=event.message_id,
        create_time=event.time,
        ctype=msg_type,
        content=msg,
        from_user_id=event.get_user_id(),
        from_user_nickname=event.sender.nickname,
        to_user_id=event.self_id,
        is_group=msg_is_group,
        group_id=session_list[1] if msg_is_group and len(session_list) != 0 else None,
        is_at=event.is_tome() if msg_is_group else False
    )

    try:
        nonebot_msg = NoneBotMessage(nonebot_raw_msg, bot)
    except NotImplementedError as e:
        logger.debug("[NoneBot] 消息创建失败： {}".format(str(e)))
        return
    context = channel._compose_context(
        nonebot_msg.ctype,
        nonebot_msg.content,
        isgroup=msg_is_group,
        msg=nonebot_msg
    )
    if context:
        channel.produce(context)


async def parse_cq_code(cq_msg: str):
    """
    解析 CQ 码，返回 JSON 格式数据
    @param cq_msg: CQ 码字符串
    """
    if cq_msg.find("[CQ:") == -1:
        return None
    else:
        if cq_msg.find("[CQ:record,") != -1:
            # 定义正则表达式规则
            pattern = r"\[CQ:(?P<cq>\w+),file=(?P<file_name>[\w.]+),path=(?P<path>.+),file_size=(?P<file_size>\d+)\]"
            # 使用正则表达式进行匹配
            match = re.match(pattern, cq_msg)

            if match:
                # 提取匹配到的数据
                cq_type = match.group("cq")
                file_name = match.group("file_name")
                path = match.group("path")
                file_size = int(match.group("file_size"))  # 转换为整数

                # 构建成 JSON 格式
                data = {
                    "CQ": cq_type,
                    "file": file_name,
                    "path": path,
                    "file_size": file_size
                }

                # 转换成 JSON 字符串
                # json_data = json.dumps(data, ensure_ascii=False)
                # logger.info(json_data)
                return data
            else:
                logger.info("No match found.")
                return None
        elif cq_msg.find("[CQ:image,") != -1:
            """
            对图片消息的解析
            """
            pattern = r"\[CQ:(?P<cq>\w+),file=(?P<file>.*?),url=(?P<url>.*?),file_size=(?P<file_size>\d+)\]"
            match = re.match(pattern, cq_msg)

            if match:
                data = {
                    "CQ": match.group("cq"),
                    "file": match.group("file"),
                    "url": match.group("url"),
                    "file_size": int(match.group("file_size"))  # 转换为整数
                }
                return data
            else:
                logger.info("No match found.")
                return None
        elif cq_msg.find("[CQ:file,") != -1:
            pattern = r"\[CQ:(?P<cq>\w+),file=(?P<file>.*?),path=(?P<path>.*?),url=(?P<url>.*?),file_id=(" \
                      r"?P<file_id>.*?),file_size=(?P<file_size>\d+)\]"
            match = re.match(pattern, cq_msg)

            if match:
                data = {
                    "CQ": match.group("cq"),
                    "file": match.group("file"),
                    "path": match.group("path"),
                    "url": match.group("url"),
                    "file_id": match.group("file_id"),
                    "file_size": int(match.group("file_size"))  # 转换为整数
                }
                return data
            else:
                logger.info("No match found.")
                return None
        else:
            logger.warning("不支持当前消息类型！")
            return None


async def convert_silk_to_mp3(input_file, output_file):
    """
    将silk语音文件转为mp3
    """
    channel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    silk_v3_tool_path = os.path.join(channel_path, "utils/silk-v3-decoder/converter.sh")
    if os.name == "nt":
        silk_v3_tool_path = os.path.join(channel_path, "utils/silk-v3-decoder/windows/silk_v3_decoder.exe")
        output_pcm_path = os.path.join(channel_path, "file/output.pcm")
        # 将silk转换为pcm
        await convert_silk_to_pcm(silk_v3_tool_path, input_file, output_pcm_path)
        # 将pcm转为MP3
        await convert_pcm_to_mp3(output_pcm_path, output_file)
        # 删除pcm临时文件
        await delete_file(output_pcm_path)
    else:
        try:
            subprocess.run([
                silk_v3_tool_path, input_file, output_file
            ], check=True, shell=True)
            logger.info(f"转换成功：{output_file}")
        except subprocess.CalledProcessError as e:
            logger.info(f"转换失败：{e}")


async def convert_silk_to_pcm(silk_path, input_file, output_file):
    """
    silk to pcm
    """
    try:
        # 使用silk_v3_decoder将silk文件转换为pcm文件
        subprocess.run(
            [silk_path, input_file, output_file],
            check=True)
        logger.info(f"转换成功：{output_file}")
    except subprocess.CalledProcessError as e:
        logger.info(f"转换失败：{e}")


async def convert_pcm_to_mp3(input_file, output_file, sample_rate=24000, channels=1):
    """
    pcm to mp3
    """
    try:
        # 使用FFmpeg将pcm文件转换为mp3文件
        subprocess.run([
            'ffmpeg',
            '-f', 's16le',  # 输入文件格式
            '-ar', str(sample_rate),  # 采样率
            '-ac', str(channels),  # 声道数
            '-i', input_file,  # 输入文件
            output_file  # 输出文件
        ], check=True)
        logger.info(f"转换成功：{output_file}")
    except subprocess.CalledProcessError as e:
        logger.info(f"转换失败：{e}")


async def delete_file(file_path):
    """
    删除临时文件
    """
    try:
        os.remove(file_path)
        logger.info(f"文件已删除：{file_path}")
    except FileNotFoundError:
        logger.info(f"文件未找到：{file_path}")
    except PermissionError:
        logger.info(f"删除文件失败，权限不足：{file_path}")
    except Exception as e:
        logger.info(f"删除文件时出错：{file_path}，错误信息：{e}")



