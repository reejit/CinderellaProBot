import html
import re

from typing import List

from telegram import Bot, Update, ParseMode
from telegram.error import BadRequest
from telegram.ext import CommandHandler, MessageHandler, Filters, run_async

import cinderella.modules.sql.blacklist_sql as sql

from cinderella import dispatcher, LOGGER
from cinderella.modules.disable import DisableAbleCommandHandler
from cinderella.modules.helper_funcs.chat_status import user_admin, user_not_admin, connection_status
from cinderella.modules.helper_funcs.extraction import extract_text
from cinderella.modules.helper_funcs.misc import split_message

BLACKLIST_GROUP = 11


@run_async
def blacklist(bot: Bot, update: Update, args: List[str]):
    msg = update.effective_message  # type: Optional[Message]
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    
    conn = connected(bot, update, chat, user.id, need_admin=False)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        if chat.type == "private":
            exit(1)
        else:
            chat_id = update.effective_chat.id
            chat_name = chat.title
    
    filter_list = tld(chat.id, "<b>Current blacklisted words in {}:</b>\n").format(chat_name)

    all_blacklisted = sql.get_chat_blacklist(chat_id)

    if len(args) > 0 and args[0].lower() == 'copy':
        for trigger in all_blacklisted:
            filter_list += "<code>{}</code>\n".format(html.escape(trigger))
    else:
        for trigger in all_blacklisted:
            filter_list += " • <code>{}</code>\n".format(html.escape(trigger))

    split_text = split_message(filter_list)
    for text in split_text:
        if filter_list == tld(chat.id, "<b>Current blacklisted words in {}:</b>\n").format(chat_name): #We need to translate
            msg.reply_text(tld(chat.id, "There are no blacklisted messages in <b>{}</b>!").format(chat_name), parse_mode=ParseMode.HTML)
            return
        msg.reply_text(text, parse_mode=ParseMode.HTML)


@run_async
@user_admin
def add_blacklist(bot: Bot, update: Update):
    msg = update.effective_message  # type: Optional[Message]
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    words = msg.text.split(None, 1)

    conn = connected(bot, update, chat, user.id)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = update.effective_chat.id
        if chat.type == "private":
            exit(1)
        else:
            chat_name = chat.title

    if len(words) > 1:
        text = words[1]
        to_blacklist = list(set(trigger.strip() for trigger in text.split("\n") if trigger.strip()))
        for trigger in to_blacklist:
            sql.add_to_blacklist(chat_id, trigger.lower())

        if len(to_blacklist) == 1:
            msg.reply_text(tld(chat.id, "Added <code>{}</code> to the blacklist in <b>{}</b>!").format(html.escape(to_blacklist[0]), chat_name),
                           parse_mode=ParseMode.HTML)

        else:
            msg.reply_text(tld(chat.id, 
             "Added <code>{}</code> to the blacklist in <b>{}</b>!").format(len(to_blacklist)), chat_name, parse_mode=ParseMode.HTML)

    else:
        msg.reply_text(tld(chat.id, "Tell me what words you would like to add to the blacklist."))


@run_async
@user_admin
def unblacklist(bot: Bot, update: Update):
    msg = update.effective_message  # type: Optional[Message]
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    words = msg.text.split(None, 1)

    conn = connected(bot, update, chat, user.id)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = update.effective_chat.id
        if chat.type == "private":
            exit(1)
        else:
            chat_name = chat.title

    if len(words) > 1:
        text = words[1]
        to_unblacklist = list(set(trigger.strip() for trigger in text.split("\n") if trigger.strip()))
        successful = 0
        for trigger in to_unblacklist:
            success = sql.rm_from_blacklist(chat_id, trigger.lower())
            if success:
                successful += 1

        if len(to_unblacklist) == 1:
            if successful:
                msg.reply_text(tld(chat.id, "Removed <code>{}</code> from the blacklist in <b>{}</b>!").format(html.escape(to_unblacklist[0]), chat_name),
                               parse_mode=ParseMode.HTML)
            else:
                msg.reply_text(tld(chat.id, "This isn't a blacklisted trigger...!"))

        elif successful == len(to_unblacklist):
            msg.reply_text(tld(chat.id, 
                "Removed <code>{}</code> triggers from the blacklist in <b>{}</b>!").format(
                    successful, chat_name), parse_mode=ParseMode.HTML)

        elif not successful:
            msg.reply_text(tld(chat.id, 
                "None of these triggers were exist, so they weren't removed.").format(
                    successful, len(to_unblacklist) - successful), parse_mode=ParseMode.HTML)

        else:
            msg.reply_text(tld(chat.id, 
                "Removed <code>{}</code> triggers from the blacklist in <b>{}</b>! {} did not exist, "
                "so were not removed.").format(successful, chat_name, len(to_unblacklist) - successful),
                parse_mode=ParseMode.HTML)
    else:
        msg.reply_text(tld(chat.id, "Tell me what words you would like to remove from the blacklist."))


@run_async
@user_not_admin
def del_blacklist(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    message = update.effective_message  # type: Optional[Message]
    to_match = extract_text(message)
    if not to_match:
        return

    chat_filters = sql.get_chat_blacklist(chat.id)
    for trigger in chat_filters:
        pattern = r"( |^|[^\w])" + re.escape(trigger) + r"( |$|[^\w])"
        if re.search(pattern, to_match, flags=re.IGNORECASE):
            try:
                message.delete()
            except BadRequest as excp:
                if excp.message == "Message to delete not found":
                    pass
                else:
                    LOGGER.exception("Error while deleting blacklist message.")
            break


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(bot, update, chat, chatP, user):
    blacklisted = sql.num_blacklist_chat_filters(chat.id)
    return "There are {} blacklisted words.".format(blacklisted)


def __stats__():
    return "{} blacklist triggers, across {} chats.".format(sql.num_blacklist_filters(),
                                                            sql.num_blacklist_filter_chats())

def __import_data__(chat_id, data):
    # set chat blacklist
    blacklist = data.get('blacklist', {})
    for trigger in blacklist:
        sql.add_to_blacklist(chat_id, trigger)


__mod_name__ = "Word Blacklists"

BLACKLIST_HANDLER = DisableAbleCommandHandler("blacklist", blacklist, pass_args=True, admin_ok=True)
ADD_BLACKLIST_HANDLER = CommandHandler("addblacklist", add_blacklist)
UNBLACKLIST_HANDLER = CommandHandler(["unblacklist", "rmblacklist"], unblacklist)
BLACKLIST_DEL_HANDLER = MessageHandler(
    (Filters.text | Filters.command | Filters.sticker | Filters.photo) & Filters.group, del_blacklist, edited_updates=True)
dispatcher.add_handler(BLACKLIST_HANDLER)
dispatcher.add_handler(ADD_BLACKLIST_HANDLER)
dispatcher.add_handler(UNBLACKLIST_HANDLER)
dispatcher.add_handler(BLACKLIST_DEL_HANDLER, group=BLACKLIST_GROUP)

__mod_name__ = "WORD BLACKLISTS"
__handlers__ = [BLACKLIST_HANDLER, ADD_BLACKLIST_HANDLER, UNBLACKLIST_HANDLER, (BLACKLIST_DEL_HANDLER, BLACKLIST_GROUP)]
