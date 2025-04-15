import os
import json
import datetime
import logging
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token - replace with your actual token from BotFather
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

class EloTracker:
    def __init__(self, data_file="pingpong_elo.json", k_factor=32, default_rating=1200):
        """
        Initialize the ELO tracker.
        
        Args:
            data_file: File to store player data
            k_factor: How quickly ratings change (higher = faster changes)
            default_rating: Starting rating for new players
        """
        self.data_file = data_file
        self.k_factor = k_factor
        self.default_rating = default_rating
        self.players = {}
        self.match_history = []
        
        # Load existing data if available
        self.load_data()
    
    def load_data(self) -> None:
        """Load player data from file if it exists."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.players = data.get('players', {})
                    self.match_history = data.get('match_history', [])
            except Exception as e:
                logger.error(f"Error loading data: {e}")
                # Initialize with empty data
                self.players = {}
                self.match_history = []
    
    def save_data(self) -> None:
        """Save player data to file."""
        data = {
            'players': self.players,
            'match_history': self.match_history
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_player(self, name: str) -> None:
        """
        Add a new player with default rating.
        
        Args:
            name: Player name
        """
        if name not in self.players:
            self.players[name] = {
                'rating': self.default_rating,
                'matches_played': 0,
                'wins': 0,
                'losses': 0
            }
            logger.info(f"Added player {name} with initial rating {self.default_rating}")
            self.save_data()
            return True
        else:
            logger.info(f"Player {name} already exists!")
            return False
    
    def calculate_expected_score(self, rating_a: float, rating_b: float) -> float:
        """
        Calculate the expected score for player A against player B.
        
        Args:
            rating_a: Rating of player A
            rating_b: Rating of player B
            
        Returns:
            Expected score (between 0 and 1)
        """
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    
    def update_ratings(self, winner: str, loser: str) -> Tuple[float, float, float, float]:
        """
        Update ratings based on a match result.
        
        Args:
            winner: Name of the winning player
            loser: Name of the losing player
            
        Returns:
            Tuple of (winner's new rating, loser's new rating, winner_rating_change, loser_rating_change)
        """
        # Add players if they don't exist
        for player in [winner, loser]:
            if player not in self.players:
                self.add_player(player)
        
        # Get current ratings
        winner_rating = self.players[winner]['rating']
        loser_rating = self.players[loser]['rating']
        
        # Calculate expected scores
        winner_expected = self.calculate_expected_score(winner_rating, loser_rating)
        loser_expected = self.calculate_expected_score(loser_rating, winner_rating)
        
        # Update ratings
        new_winner_rating = winner_rating + self.k_factor * (1 - winner_expected)
        new_loser_rating = loser_rating + self.k_factor * (0 - loser_expected)
        
        # Calculate rating changes
        winner_rating_change = new_winner_rating - winner_rating
        loser_rating_change = new_loser_rating - loser_rating
        
        # Round to integers
        new_winner_rating = round(new_winner_rating)
        new_loser_rating = round(new_loser_rating)
        
        # Update player stats
        self.players[winner]['rating'] = new_winner_rating
        self.players[winner]['matches_played'] += 1
        self.players[winner]['wins'] += 1
        
        self.players[loser]['rating'] = new_loser_rating
        self.players[loser]['matches_played'] += 1
        self.players[loser]['losses'] += 1
        
        # Record match in history
        match_record = {
            'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'winner': winner,
            'loser': loser,
            'winner_old_rating': winner_rating,
            'winner_new_rating': new_winner_rating,
            'loser_old_rating': loser_rating,
            'loser_new_rating': new_loser_rating
        }
        self.match_history.append(match_record)
        
        # Save updated data
        self.save_data()
        
        return new_winner_rating, new_loser_rating, winner_rating_change, loser_rating_change
    
    def get_player_ranking(self) -> List[Dict]:
        """
        Get a list of players sorted by rating.
        
        Returns:
            List of player dictionaries with name and rating
        """
        ranking = []
        for name, data in self.players.items():
            ranking.append({
                'name': name,
                'rating': data['rating'],
                'matches': data['matches_played'],
                'wins': data['wins'],
                'losses': data['losses'],
                'win_rate': round(data['wins'] / data['matches_played'] * 100, 1) if data['matches_played'] > 0 else 0
            })
        
        # Sort by rating (descending)
        ranking.sort(key=lambda x: x['rating'], reverse=True)
        
        # Add rank
        for i, player in enumerate(ranking):
            player['rank'] = i + 1
            
        return ranking
    
    def generate_rankings_message(self) -> str:
        """
        Generate a Telegram-friendly rankings message.
        
        Returns:
            Formatted string with current rankings
        """
        rankings = self.get_player_ranking()
        
        if not rankings:
            return "No players registered yet. Use /addplayer to add players."
        
        message = "🏓 *PING PONG ELO RANKINGS* 🏓\n\n"
        
        for player in rankings:
            message += f"{player['rank']}. {player['name']}: {player['rating']} ELO "
            message += f"({player['wins']}-{player['losses']}, {player['win_rate']}%)\n"
            
        message += f"\n_Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        
        return message

    def get_player_choices(self) -> List[str]:
        """Get a list of all player names"""
        return sorted(list(self.players.keys()))


# Initialize the ELO tracker
elo_tracker = EloTracker()

# Track ongoing match reporting for each user
ongoing_matches = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "🏓 Welcome to the Ping Pong ELO Bot! 🏓\n\n"
        "This bot helps you track ELO ratings for ping pong matches.\n\n"
        "Commands:\n"
        "/match - Record a match result\n"
        "/rankings - Show current rankings\n"
        "/addplayer - Add a new player\n"
        "/help - Show this help message"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "🏓 Ping Pong ELO Bot Commands 🏓\n\n"
        "/match - Record a match result\n"
        "/rankings - Show current rankings\n"
        "/addplayer - Add a new player\n"
        "/help - Show this help message"
    )

async def add_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new player."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a player name.\n"
            "Example: /addplayer John"
        )
        return
    
    player_name = " ".join(context.args)
    
    if elo_tracker.add_player(player_name):
        await update.message.reply_text(f"✅ Added player {player_name} with initial rating {elo_tracker.default_rating}")
    else:
        await update.message.reply_text(f"⚠️ Player {player_name} already exists!")

async def show_rankings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current rankings."""
    rankings_message = elo_tracker.generate_rankings_message()
    await update.message.reply_text(rankings_message, parse_mode="Markdown")

async def record_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the match recording process."""
    user_id = update.effective_user.id
    
    # Get list of players
    players = elo_tracker.get_player_choices()
    
    if not players:
        await update.message.reply_text(
            "⚠️ No players registered yet. Use /addplayer to add players first."
        )
        return
    
    # Create buttons for player selection
    keyboard = []
    for player in players:
        keyboard.append([InlineKeyboardButton(player, callback_data=f"winner_{player}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store the step in the ongoing_matches dictionary
    ongoing_matches[user_id] = {"step": "select_winner"}
    
    await update.message.reply_text("Who won the match?", reply_markup=reply_markup)

async def quick_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Record a match using a quick format: /match Player1 beats Player2."""
    if not context.args or len(" ".join(context.args).split(" beats ")) != 2:
        await update.message.reply_text(
            "Please use the format: /match Player1 beats Player2"
        )
        return
    
    match_text = " ".join(context.args)
    parts = match_text.split(" beats ")
    
    winner = parts[0].strip()
    loser = parts[1].strip()
    
    # Check if both players exist
    for player in [winner, loser]:
        if player not in elo_tracker.players:
            elo_tracker.add_player(player)
            await update.message.reply_text(f"Added new player: {player}")
    
    # Record the match
    try:
        new_winner_rating, new_loser_rating, winner_change, loser_change = elo_tracker.update_ratings(winner, loser)
        
        response = f"✅ Match recorded: {winner} beat {loser}\n\n"
        response += f"{winner}: {new_winner_rating} ELO (+{round(winner_change)})\n"
        response += f"{loser}: {new_loser_rating} ELO ({round(loser_change)})\n\n"
        response += "Use /rankings to see full standings"
        
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Error recording match: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # If user doesn't have an ongoing match, ignore
    if user_id not in ongoing_matches:
        await query.edit_message_text(text="Session expired. Please start again with /match")
        return
    
    # Get the current step for this user
    step = ongoing_matches[user_id]["step"]
    
    if step == "select_winner":
        winner = callback_data.replace("winner_", "")
        ongoing_matches[user_id]["winner"] = winner
        ongoing_matches[user_id]["step"] = "select_loser"
        
        # Create keyboard for loser selection (exclude winner)
        players = elo_tracker.get_player_choices()
        keyboard = []
        for player in players:
            if player != winner:  # Don't allow selecting the same player as winner and loser
                keyboard.append([InlineKeyboardButton(player, callback_data=f"loser_{player}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"Selected winner: {winner}\n\nWho lost the match?",
            reply_markup=reply_markup
        )
        
    elif step == "select_loser":
        loser = callback_data.replace("loser_", "")
        winner = ongoing_matches[user_id]["winner"]
        
        # Record the match
        try:
            new_winner_rating, new_loser_rating, winner_change, loser_change = elo_tracker.update_ratings(winner, loser)
            
            response = f"✅ Match recorded: {winner} beat {loser}\n\n"
            response += f"{winner}: {new_winner_rating} ELO (+{round(winner_change)})\n"
            response += f"{loser}: {new_loser_rating} ELO ({round(loser_change)})\n\n"
            response += "Use /rankings to see full standings"
            
            await query.edit_message_text(text=response)
            
            # Clean up
            del ongoing_matches[user_id]
            
        except Exception as e:
            await query.edit_message_text(text=f"❌ Error recording match: {e}")
            # Clean up on error
            del ongoing_matches[user_id]

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addplayer", add_player))
    application.add_handler(CommandHandler("rankings", show_rankings))
    application.add_handler(CommandHandler("match", record_match))
    application.add_handler(CommandHandler("quickmatch", quick_match))
    
    # Add callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
