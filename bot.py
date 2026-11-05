
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ================= CONFIGURATION =================

BOT_TOKEN = "9264158150:AAFDGpFG2GdhgdIY3JT8WcAbBz-3NIU723k"
ADMIN_IDS = [8324805361]  # Apna Telegram numeric ID
UPI_ID = "taushifmd@fam"
PAYEE_NAME = "MD TAUSHIF"

DB = "bot_database.db"


# ================= DATABASE =================

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def setup():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            referrer INTEGER
        );

        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            file_id TEXT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            utr TEXT UNIQUE,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            note TEXT,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            date TEXT
        );
        """)


def admin(uid):
    return uid in ADMIN_IDS


def balance(uid):
    with connect() as con:
        row = con.execute(
            "SELECT balance FROM users WHERE id=?", (uid,)
        ).fetchone()
        return row["balance"] if row else 0


def credit(uid, amount, note):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,)
        )
        con.execute(
            "UPDATE users SET balance=balance+? WHERE id=?",
            (amount, uid)
        )
        con.execute(
            "INSERT INTO transactions(user_id,amount,note,date) VALUES(?,?,?,?)",
            (uid, amount, note, datetime.now().isoformat())
        )


def debit(uid, amount, note):
    credit(uid, -amount, note)


# ================= MENUS =================

def menu(uid):
    buttons = [
        [InlineKeyboardButton("🛍 Catalog", callback_data="catalog"),
         InlineKeyboardButton("🔎 Search", callback_data="search")],

        [InlineKeyboardButton("💰 Wallet", callback_data="wallet"),
         InlineKeyboardButton("➕ Add Balance", callback_data="add")],

        [InlineKeyboardButton("📦 My Orders", callback_data="orders"),
         InlineKeyboardButton("🧾 Transactions", callback_data="transactions")],

        [InlineKeyboardButton("🎁 Refer & Earn", callback_data="refer"),
         InlineKeyboardButton("❓ Help", callback_data="help")]
    ]

    if admin(uid):
        buttons.append([
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")
        ])

    return InlineKeyboardMarkup(buttons)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add User Balance", callback_data="credit")],
        [InlineKeyboardButton("➖ Deduct Balance", callback_data="debit")],
        [InlineKeyboardButton("⏳ Pending Payments", callback_data="pending")],
        [InlineKeyboardButton("➕ Add Product", callback_data="addproduct")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="home")]
    ])


# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    referrer = None
    if context.args:
        match = re.fullmatch(r"ref_(\d+)", context.args[0])
        if match:
            referrer = int(match.group(1))

    with connect() as con:
        exists = con.execute(
            "SELECT id FROM users WHERE id=?", (uid,)
        ).fetchone()

        if not exists:
            if referrer == uid:
                referrer = None

            con.execute(
                "INSERT INTO users(id,referrer) VALUES(?,?)",
                (uid, referrer)
            )

    await update.message.reply_text(
        "👋 Welcome to File Store Bot!\n\nChoose an option:",
        reply_markup=menu(uid)
    )


# ================= BUTTON HANDLER =================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data

    if data == "home":
        await q.edit_message_text("Main Menu", reply_markup=menu(uid))

    elif data == "wallet":
        await q.edit_message_text(
            f"💰 Your Balance: ₹{balance(uid):.2f}",
            reply_markup=menu(uid)
        )

    elif data == "add":
        context.user_data["state"] = "amount"

        await q.edit_message_text(
            f"Enter amount to add.\n\n"
            f"UPI ID: {UPI_ID}\n"
            f"Payee: {PAYEE_NAME}\n\n"
            "Payment ke baad UTR bhejna hoga."
        )

    elif data == "catalog":
        with connect() as con:
            products = con.execute(
                "SELECT * FROM products ORDER BY id DESC"
            ).fetchall()

        if not products:
            await q.edit_message_text(
                "No products available.",
                reply_markup=menu(uid)
            )
            return

        keyboard = []

        for p in products:
            keyboard.append([
                InlineKeyboardButton(
                    f"{p['name']} - ₹{p['price']}",
                    callback_data=f"product_{p['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("⬅️ Back", callback_data="home")
        ])

        await q.edit_message_text(
            "🛍 Available Products:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("product_"):
        pid = int(data.split("_")[1])

        with connect() as con:
            p = con.execute(
                "SELECT * FROM products WHERE id=?", (pid,)
            ).fetchone()

        if not p:
            await q.edit_message_text("Product not found.")
            return

        keyboard = [
            [InlineKeyboardButton(
                f"🛒 Buy ₹{p['price']}",
                callback_data=f"buy_{pid}"
            )],
            [InlineKeyboardButton("⬅️ Catalog", callback_data="catalog")]
        ]

        await q.edit_message_text(
            f"📦 {p['name']}\n\n"
            f"{p['description']}\n\n"
            f"Price: ₹{p['price']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("buy_"):
        pid = int(data.split("_")[1])

        with connect() as con:
            p = con.execute(
                "SELECT * FROM products WHERE id=?", (pid,)
            ).fetchone()

        if not p:
            await q.edit_message_text("Product not found.")
            return

        if balance(uid) < p["price"]:
            await q.edit_message_text(
                "❌ Insufficient Balance!\n"
                "Please add balance first.",
                reply_markup=menu(uid)
            )
            return

        debit(uid, p["price"], f"Purchase product {pid}")

        with connect() as con:
            con.execute(
                "INSERT INTO orders(user_id,product_id,date) VALUES(?,?,?)",
                (uid, pid, datetime.now().isoformat())
            )

        await context.bot.send_document(
            chat_id=uid,
            document=p["file_id"],
            caption=f"✅ Purchase Successful: {p['name']}"
        )

        await q.edit_message_text(
            "✅ Order completed!",
            reply_markup=menu(uid)
        )

    elif data == "search":
        context.user_data["state"] = "search"
        await q.edit_message_text("Send product name to search:")

    elif data == "orders":
        with connect() as con:
            rows = con.execute("""
                SELECT orders.id, products.name
                FROM orders
                JOIN products ON products.id=orders.product_id
                WHERE orders.user_id=?
                ORDER BY orders.id DESC LIMIT 15
            """, (uid,)).fetchall()

        msg = "📦 Your Orders:\n"
        msg += "\n".join(
            f"#{r['id']} - {r['name']}" for r in rows
        ) if rows else "No orders yet."

        await q.edit_message_text(msg, reply_markup=menu(uid))

    elif data == "transactions":
        with connect() as con:
            rows = con.execute(
                "SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 15",
                (uid,)
            ).fetchall()

        msg = "🧾 Transactions:\n"
        msg += "\n".join(
            f"₹{r['amount']:.2f} - {r['note']}" for r in rows
        ) if rows else "No transactions yet."

        await q.edit_message_text(msg, reply_markup=menu(uid))

    elif data == "refer":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start=ref_{uid}"

        await q.edit_message_text(
            f"🎁 Your Referral Link:\n{link}",
            reply_markup=menu(uid)
        )

    elif data == "help":
        await q.edit_message_text(
            "For help, contact the bot admin.",
            reply_markup=menu(uid)
        )

    # ADMIN PANEL

    elif data == "admin":
        if admin(uid):
            await q.edit_message_text(
                "⚙️ ADMIN PANEL",
                reply_markup=admin_menu()
            )

    elif data in ("credit", "debit"):
        if not admin(uid):
            return

        context.user_data["state"] = data

        await q.edit_message_text(
            "Send details in this format:\n\n"
            "USER_ID AMOUNT\n\n"
            "Example:\n123456789 100"
        )

    elif data == "addproduct":
        if not admin(uid):
            return

        context.user_data["state"] = "product"

        await q.edit_message_text(
            "Send product details in this format:\n\n"
            "NAME | PRICE | FILE_ID | DESCRIPTION\n\n"
            "Example:\n"
            "Premium PDF | 50 | FILE_ID_HERE | Study material"
        )

    elif data == "pending":
        if not admin(uid):
            return

        with connect() as con:
            rows = con.execute(
                "SELECT * FROM payments WHERE status='pending'"
            ).fetchall()

        if not rows:
            await q.edit_message_text(
                "No pending payments.",
                reply_markup=admin_menu()
            )
            return

        keyboard = []

        for r in rows:
            keyboard.append([
                InlineKeyboardButton(
                    f"#{r['id']} ₹{r['amount']} User {r['user_id']}",
                    callback_data=f"review_{r['id']}"
                )
            ])

        await q.edit_message_text(
            "Pending Payments:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("review_"):
        if not admin(uid):
            return

        pid = int(data.split("_")[1])

        with connect() as con:
            p = con.execute(
                "SELECT * FROM payments WHERE id=?", (pid,)
            ).fetchone()

        if not p or p["status"] != "pending":
            await q.edit_message_text("Already processed.")
            return

        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{pid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{pid}")
        ]]

        await q.edit_message_text(
            f"Payment #{pid}\n"
            f"User: {p['user_id']}\n"
            f"Amount: ₹{p['amount']}\n"
            f"UTR: {p['utr']}\n\n"
            "Verify actual bank credit before approving.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith(("approve_", "reject_")):
        if not admin(uid):
            return

        action, pid = data.split("_")
        pid = int(pid)

        with connect() as con:
            p = con.execute(
                "SELECT * FROM payments WHERE id=?", (pid,)
            ).fetchone()

            if not p or p["status"] != "pending":
                await q.edit_message_text("Already processed.")
                return

            status = "approved" if action == "approve" else "rejected"

            con.execute(
                "UPDATE payments SET status=? WHERE id=?",
                (status, pid)
            )

        if action == "approve":
            credit(p["user_id"], p["amount"], f"Payment UTR {p['utr']}")
            await context.bot.send_message(
                p["user_id"],
                f"✅ ₹{p['amount']} added to your wallet!"
            )
        else:
            await context.bot.send_message(
                p["user_id"],
                f"❌ Payment request #{pid} rejected."
            )

        await q.edit_message_text(
            f"Payment {status}.",
            reply_markup=admin_menu()
        )

    elif data == "stats":
        if not admin(uid):
            return

        with connect() as con:
            users = con.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]

            products = con.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]

        await q.edit_message_text(
            f"📊 Statistics\n\nUsers: {users}\nProducts: {products}",
            reply_markup=admin_menu()
        )


# ================= TEXT HANDLER =================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text.strip()
    state = context.user_data.get("state")

    if state == "amount":
        try:
            amount = float(msg)
            if amount <= 0 or amount > 100000:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Enter a valid amount.")
            return

        context.user_data["amount"] = amount
        context.user_data["state"] = "utr"

        url = (
            f"upi://pay?pa={quote(UPI_ID)}"
            f"&pn={quote(PAYEE_NAME)}&am={amount}&cu=INR"
        )

        await update.message.reply_text(
            f"Pay ₹{amount} to UPI ID:\n{UPI_ID}\n\n"
            "After payment, send your UTR number.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📲 Pay using UPI", url=url)
            ]])
        )

    elif state == "utr":
        if not re.fullmatch(r"[A-Za-z0-9]{8,30}", msg):
            await update.message.reply_text("Invalid UTR. Try again.")
            return

        amount = context.user_data.get("amount")

        try:
            with connect() as con:
                cur = con.execute(
                    "INSERT INTO payments(user_id,amount,utr) VALUES(?,?,?)",
                    (uid, amount, msg)
                )
                pid = cur.lastrowid
        except sqlite3.IntegrityError:
            await update.message.reply_text("This UTR was already submitted.")
            return

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Payment request #{pid} submitted.\n"
            "Admin verification is pending.",
            reply_markup=menu(uid)
        )

        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    aid,
                    f"New payment request #{pid}\n"
                    f"User: {uid}\nAmount: ₹{amount}\nUTR: {msg}"
                )
            except Exception:
                pass

    elif state == "search":
        context.user_data.clear()

        with connect() as con:
            rows = con.execute(
                "SELECT id,name,price FROM products WHERE name LIKE ?",
                (f"%{msg}%",)
            ).fetchall()

        keyboard = [[
            InlineKeyboardButton(
                f"{r['name']} - ₹{r['price']}",
                callback_data=f"product_{r['id']}"
            )
        ] for r in rows]

        await update.message.reply_text(
            "Search Results:" if rows else "No products found.",
            reply_markup=InlineKeyboardMarkup(keyboard) if rows else menu(uid)
        )

    elif state in ("credit", "debit"):
        if not admin(uid):
            return

        try:
            target, amount = msg.split()
            target = int(target)
            amount = float(amount)

            if amount <= 0 or amount > 1000000:
                raise ValueError

        except ValueError:
            await update.message.reply_text(
                "Format: USER_ID AMOUNT\nExample: 123456789 100"
            )
            return

        if state == "credit":
            credit(target, amount, f"Admin credit by {uid}")
            action = "added"
        else:
            if balance(target) < amount:
                await update.message.reply_text("User has insufficient balance.")
                return

            debit(target, amount, f"Admin deduction by {uid}")
            action = "deducted"

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ ₹{amount} {action} for user {target}.\n"
            f"New balance: ₹{balance(target)}",
            reply_markup=admin_menu()
        )

        try:
            await context.bot.send_message(
                target, f"Admin has {action} ₹{amount} in your wallet."
            )
        except Exception:
            pass

    elif state == "product":
        if not admin(uid):
            return

        try:
            name, price, file_id, description = [
                x.strip() for x in msg.split("|", 3)
            ]

            price = float(price)
            if not name or not file_id or price < 0:
                raise ValueError

            with connect() as con:
                con.execute(
                    "INSERT INTO products(name,price,file_id,description) VALUES(?,?,?,?)",
                    (name, price, file_id, description)
                )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ Product added successfully!",
                reply_markup=admin_menu()
            )

        except Exception:
            await update.message.reply_text(
                "Invalid format.\n"
                "NAME | PRICE | FILE_ID | DESCRIPTION"
            )

    else:
        await update.message.reply_text(
            "Use /start to open the bot menu.",
            reply_markup=menu(uid)
        )


# ================= FILE ID =================

async def getfileid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        return

    if update.message.document:
        await update.message.reply_text(
            "File ID:\n" + update.message.document.file_id
        )
    else:
        await update.message.reply_text(
            "Send a document, then use /getfileid."
        )


# ================= MAIN =================

def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN":
        raise SystemExit("Please enter your Telegram bot token.")

    if not ADMIN_IDS or ADMIN_IDS == [123456789]:
        raise SystemExit("Please enter your actual numeric admin ID.")

    setup()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getfileid", getfileid))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, getfileid))

    print("BOT IS RUNNING...")
    app.run_polling()


if __name__ == "__main__":
    main()
