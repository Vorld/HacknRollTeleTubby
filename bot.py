import logging
import os
from dotenv import load_dotenv
from telegram import Chat, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram import Chat, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
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


uri = "mongodb+srv://admin:" + MONGOOSE_KEY + "@messages.5xaf5.mongodb.net/?retryWrites=true&w=majority&appName=messages"

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
    selected_channels = context.user_data.get(chat_id, set())
    print(selected_channels)
    if not selected_channels:
        await context.bot.send_message(chat_id, "No channels or groups selected. Use /showall to select them.")
        return

    # Provide options for summarizing selected groups/channels
    keyboard = [
        [InlineKeyboardButton(f"Summarize Last 24 Hours - {channel}", callback_data=f"briefing_24h_{channel}")]
        for channel in selected_channels
    ] + [
        [InlineKeyboardButton(f"Summarize Last 100 Messages - {channel}", callback_data=f"briefing_100_{channel}")]
        for channel in selected_channels
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id,
        "Choose how you'd like to summarize messages for each selected group/channel:",
        reply_markup=reply_markup
    )

async def fetch_briefing(update, context):
    query = update.callback_query
    data = query.data
    # print(data)
    _, option, channel_name = data.split("_", 2)
    print("Channel Name", channel_name)
    _, channel_name = channel_name.split("_", 1)

    from datetime import datetime, timedelta
    time_limit = datetime.now() - timedelta(hours=24)

    if option == "24h":
        query_filter = {"chat_name": channel_name, "date": {"$gte": time_limit}}
        result = collection.find(query_filter).sort("date", -1)
    elif option == "100":
        query_filter = {"chat_name": channel_name}

        result = collection.find(query_filter).sort("date", -1).limit(100)
    else:
        await query.answer("Invalid option.")
        return

    messages = [doc['text'] for doc in result if 'text' in doc]

    if not messages:
        await query.answer("No messages found to summarize.")
        return

    # Prepare the prompt for Gemini
    combined_messages = "\n".join(messages)
    prompt = f"Summarize the following messages into a concise summary highlighting key points:\n\n{combined_messages}"

    try:
        # Generate the summary using Gemini
        summary_response = model.generate_content(prompt)
        summary = summary_response.text.strip()
        
        if not summary:
            summary = "I couldn't generate a summary for these messages."
        
        # Send the summary back to the user
        await context.bot.send_message(query.message.chat_id, f"\U0001F4DD *Summary:*\n{summary}", parse_mode='Markdown')
    except Exception as e:
        print(f"Error during summarization: {e}")
        await context.bot.send_message(query.message.chat_id, "An error occurred while generating the summary.")

    await query.answer("Summary generated.")



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

''' ALL THE CHANNEL TRACKING FROM https://docs.python-telegram-bot.org/en/stable/examples.html#examples-chatmemberbot'''
''' ALL THE CHANNEL TRACKING FROM https://docs.python-telegram-bot.org/en/stable/examples.html#examples-chatmemberbot'''

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
    """Shows which chats the bot is in, grouped by user, group, and channel using only IDs."""
    user_ids = list(context.bot_data.setdefault("user_ids", set()))
    group_ids = list(context.bot_data.setdefault("group_ids", set()))
    group_names = list(context.bot_data.setdefault("group_names", set()))
    group_names = list(context.bot_data.setdefault("group_names", set()))
    channel_ids = list(context.bot_data.setdefault("channel_ids", set()))
    channel_names = list(context.bot_data.setdefault("channel_names", set()))
    channel_names = list(context.bot_data.setdefault("channel_names", set()))

    text = (
        f"@{context.bot.username} is currently in a conversation with the following IDs:\n\n"
        f"\U0001F464 *Users:* {', '.join(map(str, user_ids)) or 'None'}\n"
        f"\U0001F465 *Groups:* {', '.join(map(str, group_names)) or 'None'}\n"
        f"\U0001F4E2 *Channels:* {', '.join(map(str, channel_names)) or 'None'}\n"
    )
    
    chat_id = update.message.chat_id
    selected_chats = context.user_data.get(chat_id, set())

    if not group_names and not channel_names:
        await context.bot.send_message(chat_id, "No groups or channels available.")
        return

    # Create separate sections for groups and channels using IDs only
    keyboard = []
    print("Group IDs", group_ids)
    if group_ids:
        keyboard.append([InlineKeyboardButton("\U0001F465 Groups", callback_data="groups_header")])
        keyboard.extend(
            [
                [InlineKeyboardButton(f"{'✅' if str(group) in selected_chats else '➖'} Group {group}", callback_data=f"toggle_group_{group}")]
                for group in group_names
            ]
        )
    
    if channel_ids:
        keyboard.append([InlineKeyboardButton("\U0001F4E2 Channels", callback_data="channels_header")])
        keyboard.extend(
            [
                [InlineKeyboardButton(f"{'✅' if str(channel) in selected_chats else '➖'} Channel {channel}", callback_data=f"toggle_channel_{channel}")]

                for channel in channel_names
            ]
        )

    # Add a submit button
    keyboard.append([InlineKeyboardButton("✅ Submit", callback_data="submit_selection")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id,
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )



async def button_handler(update, context):
    print("hi bro what it up")
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
        chat_id = update.effective_chat.id  # Store the chat ID
        text = post.text or post.caption or ""
        date = post.date

        # Tag the message
        tag = tag_message(text, previous_tags)

        # Build the document for MongoDB
        doc = {
            "chat_name": chat_name,
            "chat_id": chat_id,  # New field: chat ID
            "chat_type": chat_type,
            "sender": sender,
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
            "Inserted new message from %s (ID: %s) into MongoDB with _id=%s",
            chat_name, chat_id, result.inserted_id
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

async def show_tags(update, context):
    """Fetch all tags from the user's selected groups and channels, and display them as buttons."""
    chat_id = update.message.chat_id

    # Fetch selected chats from the user context
    selected_chats = context.user_data.get(chat_id, set())

    if not selected_chats:
        await update.message.reply_text("You have not selected any groups or channels to track tags.")
        return

    # Segregate into groups and channels
    selected_groups = [chat.split("_", 1)[1] for chat in selected_chats if chat.startswith("group_")]
    selected_channels = [chat.split("_", 1)[1] for chat in selected_chats if chat.startswith("channel_")]

    # Fetch unique tags for the selected groups and channels
    tags = collection.distinct("tag", {"chat_name": {"$in": selected_groups + selected_channels}})
    if not tags:
        await update.message.reply_text("No tags found for the selected groups or channels.")
        return

    # Create inline buttons for each tag
    keyboard = [[InlineKeyboardButton(tag, callback_data=f"tag_{tag}")] for tag in tags]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select a tag to view related messages:", reply_markup=reply_markup)



async def show_messages_for_tag(update, context):
    """Fetch and display messages that match the selected tag."""
    query = update.callback_query
    await query.answer()

    tag = query.data.split("_", 1)[1]  # Extract the tag from the callback data
    chat_id = query.message.chat_id

    # Fetch selected chats from the user context
    selected_chats = context.user_data.get(chat_id, set())

    if not selected_chats:
        await query.message.reply_text("No groups or channels selected to fetch messages.")
        return

    # Segregate into groups and channels
    selected_groups = [chat.split("_", 1)[1] for chat in selected_chats if chat.startswith("group_")]
    selected_channels = [chat.split("_", 1)[1] for chat in selected_chats if chat.startswith("channel_")]

    # Fetch messages from MongoDB for the selected tag
    messages = (
        collection.find({"tag": tag, "chat_name": {"$in": selected_groups + selected_channels}})
        .sort("date", -1)
        .limit(50)  # Limit to 50 messages
    )

    message_list = list(messages)

    if not message_list:
        await query.message.reply_text(f"No messages found for tag: {tag}.")
        return

    # Format and display the messages
    response = f"Messages for tag: **{tag}**\n\n"
    for msg in message_list:
        group_or_channel = f"📢 *{msg.get('chat_name', 'Unknown')}*"  # Group or channel name
        sender = f"👤 {msg.get('sender', 'Unknown')}"  # Sender's name
        text = f"📝 {msg.get('text', 'No text available')}"  # Message text
        date = f"📅 {msg.get('date', '').strftime('%Y-%m-%d %H:%M:%S')}" if 'date' in msg else ""

        # Append each message to the response
        response += f"{group_or_channel} | {sender}\n{text}\n{date}\n\n"

        # Handle Telegram's message length limit
        if len(response) > 3800:
            await query.message.reply_text(response[:4000], parse_mode="Markdown")
            response = ""  # Reset response to handle overflow

    if response:  # Send any remaining messages
        await query.message.reply_text(response[:4000], parse_mode="Markdown")




# Add these handlers to the bot

if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("tags", show_tags))
    application.add_handler(CommandHandler("tags", show_tags))
    application.add_handler(CommandHandler("briefing", briefing))
    application.add_handler(CommandHandler("start", start))

    # Keep track of which chats the bot is in
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CommandHandler("showall", show_channels))
    application.add_handler(CommandHandler("selected", selected_channels))
    application.add_handler(CallbackQueryHandler(fetch_briefing, pattern="^briefing_"))
    application.add_handler(CallbackQueryHandler(show_messages_for_tag, pattern="^tag_"))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_handler(CommandHandler("tags", show_tags))



    # Upload every message to ATLAS
    # General message handler without any filters
    # General message handler without any filters
    application.add_handler(MessageHandler(filters.ALL, store_channel_message))

    application.run_polling(allowed_updates=Update.ALL_TYPES)
