from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR
from bot.helper.telegram_helper.button_build import ButtonMaker


import shutil
import psutil
from telegram.error import RetryAfter
from telegram.ext import CallbackQueryHandler
from telegram.message import Message
from telegram.update import Update
from bot import *

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "𝐔𝐩𝐥𝐨𝐚𝐝𝐢𝐧𝐠📤"
    STATUS_DOWNLOADING = "𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠📥"
    STATUS_CLONING = "𝐂𝐥𝐨𝐧𝐢𝐧𝐠♻️"
    STATUS_WAITING = "𝐐𝐮𝐞𝐮𝐞𝐝💤"
    STATUS_FAILED = "𝐅𝐚𝐢𝐥𝐞𝐝 🚫 𝐂𝐥𝐞𝐚𝐧𝐢𝐧𝐠 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝"
    STATUS_PAUSE = "𝐏𝐚𝐮𝐬𝐞𝐝⛔️"
    STATUS_ARCHIVING = "𝐀𝐫𝐜𝐡𝐢𝐯𝐢𝐧𝐠🔐"
    STATUS_EXTRACTING = "𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐢𝐧𝐠📂"
    STATUS_SPLITTING = "𝐒𝐩𝐥𝐢𝐭𝐭𝐢𝐧𝐠✂️"
    STATUS_CHECKING = "𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠𝐔𝐩📝"
    STATUS_SEEDING = "𝐒𝐞𝐞𝐝𝐢𝐧𝐠🌧"

    
class EngineStatus:
    STATUS_ARIA = "Aʀɪᴀ 2C v1.35.0"
    STATUS_GDRIVE = "Gᴏᴏɢʟᴇ Aᴘɪ v2.51.0"
    STATUS_MEGA = "Mᴇɢᴀsᴅᴋ v3.12.0"
    STATUS_QB = "Qʙɪᴛ v4.4.2"
    STATUS_TG = "Pʏʀᴏɢʀᴀᴍ v2.0.27"
    STATUS_YT = "Yᴛ-Dʟᴘ v2022.5.18"
    STATUS_EXT = "Exᴛʀᴀᴄᴛ"
    STATUS_SPLIT = "Fғᴍᴘᴇɢ"
    STATUS_ZIP = "7Z v16.02"
    
    
SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 7
    total = status.size_raw() / 7
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 7
    p_str = '♣' * cFull
    p_str += '♧' * (14 - cFull)
    p_str = f"├「{p_str}」"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
            msg += "\nʙᴏᴛs ᴏғ ᴛᴇʀᴍɪ ᴍɪʀʀᴏʀ\n"
            msg += f"<b>☠ 𝐓𝐨𝐭𝐚𝐥 𝐓𝐚𝐬𝐤𝐬 →</b> {tasks}"
            msg += "\n \n"
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):            
            msg += f"<b>╭─ 📂𝐅𝐢𝐥𝐞𝐍𝐚𝐦𝐞→</b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n<b>├⌬ ⌛️𝐒𝐭𝐚𝐭𝐮𝐬→</b> <i>{download.status()}</i>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n{get_progress_bar_string(download)}"
                msg += f"\n<b>├⌬ 🤫𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬→</b>{download.progress()}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n<b>├⌬ ♻️𝐂𝐥𝐨𝐧𝐞𝐝→</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"                    
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n<b>├⌬ 📤𝐃𝐨𝐧𝐞→</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                else:
                    msg += f"\n<b>├⌬ 📥𝐃𝐨𝐧𝐞→</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"\n<b>├⌬ ⚡️𝐒𝐩𝐞𝐞𝐝→</b> {download.speed()}"
                msg += f"\n<b>├⌬ ⏰𝐄𝐓𝐀→</b> {download.eta()}"
                msg += f"\n<b>├⌬ 🤔𝐄𝐥𝐚𝐩𝐬𝐞𝐝→</b>{get_readable_time(time() - download.message.date.timestamp())}"
                msg += f"\n<b>├⌬ ⚙️𝐄𝐧𝐠𝐢𝐧𝐞→</b> {download.eng()}"
                try:
                    msg += f"\n<b>├⌬ 🌱𝐒𝐞𝐞𝐝𝐬→</b> {download.aria_download().num_seeders}" \
                           f" | <b> 🎌𝐏𝐞𝐞𝐫𝐬→</b> {download.aria_download().connections}"                
                except:
                    pass
                try:
                    msg += f"\n<b>├⌬ 🌱𝐒𝐞𝐞𝐝𝐬→</b> {download.torrent_info().num_seeds}" \
                           f" | <b>🧲𝐋𝐞𝐞𝐜𝐡𝐬→</b> {download.torrent_info().num_leechs}"                
                except:
                    pass             
                msg += f'\n<b>├⌬ 🤴𝐑𝐞𝐪 𝐁𝐲→</b> <a href="tg://user?id={download.message.from_user.id}">{download.message.from_user.first_name}</a>'
                reply_to = download.message.reply_to_message    
                if reply_to:
                    msg += f"\n<b>├⌬ 🔗𝐒𝐨𝐮𝐫𝐜𝐞→<a href='https://t.me/c/{str(download.message.chat.id)[4:]}/{reply_to.message_id}'>Click Here</a></b>"
                else:
                    msg += f"\n<b>├⌬ 🔗𝐒𝐨𝐮𝐫𝐜𝐞→</b> <a href='https://t.me/c/{str(download.message.chat.id)[4:]}/{download.message.message_id}'>Click Here</a>"
                msg += f"\n<b>╰─ ❌𝐓𝐨 𝐂𝐚𝐧𝐜𝐞𝐥→</b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>├⌬ 🗂𝐒𝐢𝐳𝐞→</b>{download.size()}"
                msg += f"\n<b>├⌬ ⚡️𝐒𝐩𝐞𝐞𝐝→</b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f"\n<b>├⌬ 📤𝐃𝐨𝐧𝐞→</b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f'\n<b>├⌬ ⚙️𝐄𝐧𝐠𝐢𝐧𝐞→</b><a href="https://www.qbittorrent.org">Qbit v4.3.9</a>'
                msg += f"\n<b>├⌬ ⏲𝐑𝐚𝐭𝐢𝐨→</b>{round(download.torrent_info().ratio, 3)}"
                msg += f"\n<b>├⌬ ⏰𝐓𝐢𝐦𝐞→</b>{get_readable_time(download.torrent_info().seeding_time)}"
                msg += f"\n<b>├⌬ 🤔𝐄𝐥𝐚𝐩𝐬𝐞𝐝→</b>{get_readable_time(time() - download.message.date.timestamp())}"
                msg += f"\n╰─❌𝐓𝐨 𝐂𝐚𝐧𝐜𝐞𝐥→<code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"\n<b>├⌬ ⚙️𝐄𝐧𝐠𝐢𝐧𝐞→</b> {download.eng()}"
                msg += f"\n<b>╰─ 🗂𝐒𝐢𝐳𝐞→</b>{download.size()}"
            msg += "\n─────────────────\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>🖥️𝐂𝐏𝐔→</b> {cpu_percent()}% | <b>📦𝐑𝐀𝐌→</b> {virtual_memory().percent}%"
        
        buttons = ButtonMaker()
        buttons.sbutton("SᴛᴀᴛS", str(THREE))
        buttons.sbutton("RᴇғʀᴇsH", str(ONE))
        sbutton = InlineKeyboardMarkup(buttons.build_menu(3))
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:     
            buttons = ButtonMaker()
            buttons.sbutton("PʀᴇV", "status pre")
            buttons.sbutton(f"{PAGE_NO}/{pages}", str(ONE))
            buttons.sbutton("NᴇX", "status nex")
            buttons.sbutton("SᴛᴀᴛS", str(THREE))
            button = InlineKeyboardMarkup(buttons.build_menu(3))
            return msg + bmsg, button
        return msg + bmsg, sbutton

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_hubdrive_link(url: str):
    url = re_match(r"https?://(hubdrive)\.\S+", url)
    return bool(url)

def is_appdrive_link(url: str):
    url = re_match(r'https?://appdrive\.in/\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type

ONE, TWO, THREE = range(3)

def refresh(update, context):
    query = update.callback_query
    query.edit_message_text(text="⏳ RᴇғʀᴇsʜɪɴG Tʜᴇ SᴛᴀᴛᴜS.")
    sleep(2)
    update_all_messages()
    

def pop_up_stats(update, context):
    query = update.callback_query
    stats = bot_sys_stats()
    query.answer(text=stats, show_alert=True)

def bot_sys_stats():
    currentTime = get_readable_time(time() - botStartTime)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage(DOWNLOAD_DIR).percent
    total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    num_active = 0
    num_upload = 0
    tasks = len(download_dict)
    for stats in list(download_dict.values()):
       if stats.status() == MirrorStatus.STATUS_DOWNLOADING:
                num_active += 1
       if stats.status() == MirrorStatus.STATUS_UPLOADING:
                num_upload += 1
            
    stats = f"🅣🅔🅡🅜🅘 🅑🅞🅣 🅢🅣🅐🅣🅢"
    stats += f"""
Bᴏᴛ Uᴘᴛɪᴍᴇ :{currentTime}
Cᴘᴜ :{cpu}% Rᴀᴍ :{mem}% 
Dɪsᴋ:{disk}%

Tᴏᴛᴀʟ :{total} | Usᴇᴅ :{used}
Sᴇɴᴛ : {sent}  | Rᴇᴄᴠ: {recv}

DLs:{num_active} |ULs: {num_upload}
𝐏𝐨𝐰𝐞𝐫𝐞𝐝 𝐁𝐲 : ᴛᴇʀᴍɪ ʙᴏᴛ
"""
    return stats

dispatcher.add_handler(CallbackQueryHandler(refresh, pattern="^" + str(ONE) + "$"))
dispatcher.add_handler(
    CallbackQueryHandler(pop_up_stats, pattern="^" + str(THREE) + "$")
)
