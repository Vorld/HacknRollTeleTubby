import logging
import os
from dotenv import load_dotenv
from telegram import Chat, ChatMember, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ChatMemberHandler,
    CallbackQueryHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_API_TOKEN")

async def help(update, context):
    chat_id = update.message.chat_id

    await context.bot.send_message(chat_id, "Help!")


async def tags(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "tags!")

async def briefing(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "briefing!")

''' ALL THE CHANNEL TRACKING '''

def extract_status_change(chat_member_update):
    """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
    of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
    the status didn't change.
    """
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

    return was_member, is_member


async def track_chats(update, context):
    """Tracks the chats the bot is in."""
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    # Let's check who is responsible for the change
    cause_name = update.effective_user.full_name

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            # This may not be really needed in practice because most clients will automatically
            # send a /start command after the user unblocks the bot, and start_private_chat()
            # will add the user to "user_ids".
            # We're including this here for the sake of the example.
            logger.info("%s unblocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    elif not was_member and is_member:
        logger.info("%s added the bot to the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).add(chat.id)
        context.bot_data.setdefault("channel_names", set()).add(chat.title)
    elif was_member and not is_member:
        logger.info("%s removed the bot from the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).discard(chat.id)
        

async def show_channels(update, context):
    """Shows which chats the bot is in"""
    user_ids = ", ".join(str(uid) for uid in context.bot_data.setdefault("user_ids", set()))
    group_ids = ", ".join(str(gid) for gid in context.bot_data.setdefault("group_ids", set()))
    channel_ids = ", ".join(str(cid) for cid in context.bot_data.setdefault("channel_names", set()))

    text = (
        f"@{context.bot.username} is currently in a conversation with the user IDs {user_ids}."
        f" Moreover it is a member of the groups with IDs {group_ids} "
        f"and administrator in the channels with IDs {channel_ids}."
    )

    chat_id = update.message.chat_id
    selected_channels = context.user_data.get(chat_id, set())  # sus

    channel_names = list(context.bot_data.setdefault("channel_names", set()))


    if not channel_names:
        await update.effective_message.reply_text("No channels available.")
        return 

    keyboard = [[InlineKeyboardButton(f"{'✅' if channel in selected_channels else '➖'} {channel}",callback_data=f"toggle_{channel}")] for channel in channel_names]
    
    # Add a submit button
    keyboard.append([InlineKeyboardButton("✅ Submit", callback_data="submit_selection")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text("Select channels:", reply_markup=reply_markup)


async def button_handler(update, context):
    """Handles button clicks for selecting multiple channels."""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_selection = context.user_data.setdefault(chat_id, set())

    action, value = query.data.split("_", 1)

    if action == "toggle":
        if value in user_selection:
            user_selection.remove(value)
        else:
            user_selection.add(value)

        # Update the buttons dynamically
        await show_channels(update, context)

    elif action == "submit":
        if not user_selection:
            await query.edit_message_text("No channels selected!")
        else:
            selected_list = "\n".join(user_selection)
            await query.edit_message_text(f"✅ Selected Channels:\n{selected_list}")


async def selected_channels(update, context):
    chat_id = update.message.chat_id
    selected_channels = context.user_data.get(chat_id, set())

    if not selected_channels:
        await context.bot.send_message(chat_id, "Woops, no channels selected.")
        return

    await context.bot.send_message(chat_id, " ".join([s for s in selected_channels]))


if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("tags", tags))
    application.add_handler(CommandHandler("briefing", briefing))

    # Keep track of which chats the bot is in
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CommandHandler("show_channels", show_channels))
    application.add_handler(CommandHandler("selected_channels", selected_channels))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)