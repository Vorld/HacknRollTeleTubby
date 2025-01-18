import logging
import os
from dotenv import load_dotenv
from telegram import Chat, ChatMember, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from pymongo import MongoClient
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGOOSE_KEY = os.getenv("MONGOOSE_KEY")
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-pro')


uri = "mongodb+srv://admin:potato@messages.5xaf5.mongodb.net/?retryWrites=true&w=majority&appName=messages"

# Create a new client and connect to the server
client = MongoClient(uri)
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


db = client["DB"]  # or pick any DB name
collection = db["Messages"]


#  Set up logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def help(update, context):
    chat_id = update.message.chat_id

    await context.bot.send_message(chat_id, "Help!")


async def tags(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "tags!")

async def briefing(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "briefing!")

async def start(update, context):
    chat_id = update.message.chat_id
    bot_description = (
        "\U0001F916 *Welcome to your Telegram Decluttering Bot!*\n\n"
        "I help you manage and simplify your Telegram experience by:\n"
        "\- Reading and organizing messages from your groups and channels.\n"
        "\- Summarizing discussions to give you quick insights.\n"
        "\- Tagging messages into categories for easy navigation.\n\n"


        "*Available Commands:*\n"
        "\U0001F4AC /help \- Get help on how to use the bot.\n"
        "\U0001F4CA /tags \- View all message categories (tags).\n"
        "\U0001F4DD /briefing \- Get a summary of recent discussions.\n"
        "\U0001F4E2 /showall \- Show the channels the bot is in.\n"
        "\U0001F4E5 /selected \- View your selected channels for updates.\n"
        "\n*In essence*, I'm your one-stop Telegram agent to free you from endless chats and confusion!\n"
        "Let's get started!"
    )

    # keyboard = [
    #     [InlineKeyboardButton("\U0001F4AC Help", callback_data="help")],
    #     [InlineKeyboardButton("\U0001F4CA View Tags", callback_data="tags")],
    #     [InlineKeyboardButton("\U0001F4DD Briefing", callback_data="briefing")],
    #     [InlineKeyboardButton("\U0001F4E2 Show Channels", callback_data="show_channels")]
    # ]
    # reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id,
        bot_description,
        parse_mode='Markdown',
    )

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
    print(update)
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


previous_tags = [] 

async def store_channel_message(update, context):
    """
    Stores new messages from channels and groups in MongoDB.
    """

    if update.channel_post or update.message:
        # Handle channel posts
        if update.channel_post:
            post = update.channel_post
            chat_type = "channel"
            sender = post.sender_chat.title if post.sender_chat else "Unknown"
        
        # Handle group messages
        elif update.message and update.effective_chat.type in ["group", "supergroup"]:
            post = update.message
            chat_type = "group"
            sender = post.from_user.full_name if post.from_user else "Unknown"
        
        else:
            return  # Ignore other types of messages

        chat_name = update.effective_chat.title
        text = post.text or post.caption or ""  # Include captions for media
        date = post.date

        # Tag the message
        tag = tag_message(text, previous_tags)

        # Build the document for MongoDB
        doc = {
            "chat_name": chat_name,
            "chat_type": chat_type,  # New field: 'channel' or 'group'
            "sender": sender,        # New field: sender's name
            "text": text,
            "date": date,
            "tag": tag
        }

        # Update tags if it's new
        if tag not in previous_tags:
            previous_tags.append(tag)

        # Insert the document into the MongoDB collection
        result = collection.insert_one(doc)

        logger.info(
            "Inserted new message from %s (%s) into MongoDB with _id=%s",
            chat_name, chat_type, result.inserted_id
        )




def tag_message(message, previous_tags=None):
    """
    Tags a text message with a relevant topic using Gemini.

    Args:
        message (str): The text message to tag.
        previous_tags (list[str], optional): A list of previously used tags. Defaults to None.

    Returns:
        str: The chosen tag, or "unknown" if no topic is clear.
    """

    final = ""

    prompt_1 = f"""
    You are a helpful assistant for tagging text messages. Students in a university are busy and need information at a glance.
    Given the following text message, generate the BEST topic tag that would match the content of the message.

    Text message: {message}

    Return ONLY a single topic, do not add any other text.
    """

    first_response = model.generate_content(prompt_1).text.strip()


    # If the first response is not clear, ask for more information
    if previous_tags:
        prompt_2 = f"""
        If the tag "{first_response}" is similar to any of the following previously generated tags: {', '.join(previous_tags) if previous_tags else ""}, use the previous tag that is most similar to the content of the message. Otherwise, keep {first_response}. 
        Return ONLY the final single topic, do not add any other text. 
        """


        second_response = model.generate_content(prompt_2).text.strip()
        final = second_response
    else:
        final = first_response

    try:
        print(final)
        return final
    except Exception as e:
       print(f"An error occurred: {e}")
       return "unknown"





if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("tags", tags))
    application.add_handler(CommandHandler("briefing", briefing))
    application.add_handler(CommandHandler("start", start))

    # Keep track of which chats the bot is in
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CommandHandler("showall", show_channels))
    application.add_handler(CommandHandler("selected", selected_channels))
    application.add_handler(CallbackQueryHandler(button_handler))


    # Upload every message to ATLAS
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, store_channel_message))

    application.run_polling(allowed_updates=Update.ALL_TYPES)