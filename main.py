import asyncio
import aiohttp
import json
import random
from typing import Final, Dict, Any, List, Set
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants - REPLACE THESE FOR PRODUCTION
TOKEN: Final = ''  # Replace with your actual bot token
BOT_USERNAME: Final = '@Leetcoder77bot'
GEMINI_API_KEY: Final = ''  # Replace with your actual Gemini API key
GEMINI_API_URL: Final = ={GEMINI_API_KEY}'

# Define constant instead of duplicating "application/json" literal
CONTENT_TYPE_JSON: Final = "application/json"

# User data storage
user_chat_ids: Set[int] = set()
user_daily_problems: Dict[int, Dict[str, Any]] = {}
user_profiles: Dict[int, Dict[str, Any]] = {}

class LeetCodeService:
    def __init__(self):
        self.base_url = "https://leetcode.com/graphql"
        self.problems_cache = []
        self.cache_loaded = False

    async def get_all_problems(self) -> List[Dict[str, Any]]:
        if self.cache_loaded and self.problems_cache:
            return self.problems_cache

        query = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
            problemsetQuestionList: questionList(
                categorySlug: $categorySlug
                limit: $limit
                skip: $skip
                filters: $filters
            ) {
                total: totalNum
                questions: data {
                    acRate
                    difficulty
                    freqBar
                    frontendQuestionId: questionFrontendId
                    isFavor
                    paidOnly: isPaidOnly
                    status
                    title
                    titleSlug
                    topicTags {
                        name
                        id
                        slug
                    }
                }
            }
        }
        """
        variables = {
            "categorySlug": "",
            "skip": 0,
            "limit": 2000,
            "filters": {}
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.base_url,
                    json={"query": query, "variables": variables},
                    headers={"Content-Type": CONTENT_TYPE_JSON},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        problems = data.get('data', {}).get('problemsetQuestionList', {}).get('questions', [])
                        self.problems_cache = problems
                        self.cache_loaded = True
                        logger.info(f"Cached {len(problems)} problems")
                        return problems
                    else:
                        logger.error(f"LeetCode API returned status {response.status}")
                        return []
            except Exception as e:
                logger.error(f"Error fetching all problems: {e}")
                return []

    async def get_personalized_problems(self, user_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Get 2 personalized problems: one for speed, one for knowledge"""
        problems = await self.get_all_problems()
        if not problems:
            return {}

        free_problems = [p for p in problems if not p.get('paidOnly', True)]
        if not free_problems:
            return {}

        total_solved = user_data.get('total_solved', 0)
        
        # Determine user level and appropriate difficulties
        if total_solved < 50:
            speed_difficulties = ['Easy']
            knowledge_difficulties = ['Easy', 'Medium']
        elif total_solved < 150:
            speed_difficulties = ['Easy', 'Medium']
            knowledge_difficulties = ['Medium']
        elif total_solved < 300:
            speed_difficulties = ['Medium']
            knowledge_difficulties = ['Medium', 'Hard']
        else:
            speed_difficulties = ['Medium', 'Hard']
            knowledge_difficulties = ['Hard']

        # Speed problem: easier, high acceptance rate
        speed_candidates = [
            p for p in free_problems 
            if p.get('difficulty') in speed_difficulties and p.get('acRate', 0) > 40
        ]
        
        # Knowledge problem: challenging, lower acceptance rate
        knowledge_candidates = [
            p for p in free_problems 
            if p.get('difficulty') in knowledge_difficulties and p.get('acRate', 0) < 60
        ]

        speed_problem = random.choice(speed_candidates) if speed_candidates else random.choice(free_problems)
        knowledge_problem = random.choice(knowledge_candidates) if knowledge_candidates else random.choice(free_problems)

        return {
            'speed_problem': speed_problem,
            'knowledge_problem': knowledge_problem
        }

    async def get_user_profile(self, username: str) -> Dict[str, Any]:
        query = """
        query getUserProfile($username: String!) {
            matchedUser(username: $username) {
                username
                profile {
                    ranking
                    userAvatar
                    realName
                    aboutMe
                    school
                    websites
                    countryName
                    company
                    jobTitle
                    skillTags
                    postViewCount
                    postViewCountDiff
                    reputation
                    reputationDiff
                }
                submitStats {
                    acSubmissionNum {
                        difficulty
                        count
                        submissions
                    }
                    totalSubmissionNum {
                        difficulty
                        count
                        submissions
                    }
                }
                badges {
                    id
                    displayName
                    icon
                    creationDate
                }
            }
        }
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.base_url,
                    json={"query": query, "variables": {"username": username}},
                    headers={"Content-Type": CONTENT_TYPE_JSON},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('data', {}).get('matchedUser', {})
                    return {}
            except Exception as e:
                logger.error(f"Error fetching user profile: {e}")
                return {}

    async def get_random_problem(self, difficulty: str = None) -> Dict[str, Any]:
        problems = await self.get_all_problems()
        if not problems:
            return {}
        if difficulty:
            filtered_problems = [p for p in problems if p.get('difficulty', '').upper() == difficulty.upper()]
            problems = filtered_problems if filtered_problems else problems
        free_problems = [p for p in problems if not p.get('paidOnly', True)]
        if not free_problems:
            return {}
        return random.choice(free_problems)

    async def get_daily_challenge(self) -> Dict[str, Any]:
        query = """
        query questionOfToday {
            activeDailyCodingChallengeQuestion {
                date
                userStatus
                link
                question {
                    acRate
                    difficulty
                    freqBar
                    frontendQuestionId: questionFrontendId
                    isFavor
                    paidOnly: isPaidOnly
                    status
                    title
                    titleSlug
                    hasVideoSolution
                    hasSolution
                    topicTags {
                        name
                        id
                        slug
                    }
                }
            }
        }
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.base_url,
                    json={"query": query},
                    headers={"Content-Type": CONTENT_TYPE_JSON},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('data', {}).get('activeDailyCodingChallengeQuestion', {})
                    return {}
            except Exception as e:
                logger.error(f"Error fetching daily challenge: {e}")
                return {}

class GeminiService:
    @staticmethod
    async def generate_personalized_advice(user_data: Dict[str, Any], context: str) -> str:
        prompt = f"""
        As a LeetCode mentor, provide a detailed, personalized 4-week study plan for the following user:
        User Statistics:
        - Problems Solved: {user_data.get('total_solved', 'Unknown')}
        - Easy Problems: {user_data.get('easy_solved', 'Unknown')}
        - Medium Problems: {user_data.get('medium_solved', 'Unknown')}
        - Hard Problems: {user_data.get('hard_solved', 'Unknown')}
        - Current Ranking: {user_data.get('ranking', 'Unknown')}
        Context: {context}
        The plan should include daily targets, focus topics, and actionable strategies.
        """
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    GEMINI_API_URL,
                    json=payload,
                    headers={"Content-Type": CONTENT_TYPE_JSON},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        return "AI service temporarily unavailable. Please try again later."
            except Exception as e:
                logger.error(f"Error with Gemini API: {e}")
                return "AI service temporarily unavailable. Please try again later."

leetcode_service = LeetCodeService()
gemini_service = GeminiService()

async def safe_send_message(update: Update, text: str, parse_mode: str = None) -> None:
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Message send error: {e}")
        clean_text = text.replace('*', '').replace('_', '').replace('`', '')
        try:
            await update.message.reply_text(clean_text)
        except Exception as e2:
            logger.error(f"Fallback message send error: {e2}")

def extract_user_stats(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user statistics from profile data"""
    stats = user_data.get('submitStats', {})
    ac_stats = stats.get('acSubmissionNum', [])
    easy_solved = medium_solved = hard_solved = 0
    
    for stat in ac_stats:
        if stat['difficulty'] == 'Easy':
            easy_solved = stat['count']
        elif stat['difficulty'] == 'Medium':
            medium_solved = stat['count']
        elif stat['difficulty'] == 'Hard':
            hard_solved = stat['count']
    
    total_solved = easy_solved + medium_solved + hard_solved
    ranking = user_data.get('profile', {}).get('ranking', 'N/A')
    
    return {
        'total_solved': total_solved,
        'easy_solved': easy_solved,
        'medium_solved': medium_solved,
        'hard_solved': hard_solved,
        'ranking': ranking
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name or "there"
    user_chat_ids.add(update.effective_user.id)
    welcome_message = (
        f"🚀 Welcome {user_name}!\n\n"
        "I'm your AI-powered LeetCode companion!\n\n"
        "✨ What I can do:\n"
        "• Get personalized daily problems\n"
        "• Analyze your LeetCode profile\n"
        "• Create personalized study plans\n"
        "• Daily challenges with AI hints\n\n"
        "🎯 Quick Start:\n"
        "• /recommended2 <username> - Get 2 daily problems\n"
        "• /profile <username> - Analyze profile\n"
        "• /daily - Today's challenge\n"
        "• /help - See all commands"
    )
    await safe_send_message(update, welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🤖 LeetCode Bot Commands:\n\n"
        "📊 Profile & Analysis:\n"
        "/profile <username> - Get detailed profile analysis\n"
        "/plan <username> - Get personalized study plan\n\n"
        "🎯 Daily Recommendations:\n"
        "✅ /recommended2 <username> - Get personalized daily problems\n"
        "/solved speed - Mark speed problem as solved\n"
        "/solved knowledge - Mark knowledge problem as solved\n"
        "/mystatus - Check your daily progress\n\n"
        "🎲 Random Problems:\n"
        "/random - Get any random problem\n"
        "/easy - Get random easy problem\n"
        "/medium - Get random medium problem\n"
        "/hard - Get random hard problem\n\n"
        "📅 Daily Features:\n"
        "/daily - Today's daily challenge\n\n"
        "🛠️ Utilities:\n"
        "/start - Restart the bot\n"
        "/help - Show this help\n\n"
        "💡 Tips:\n"
        "• Daily problems adapt to your skill level\n"
        "• Speed problems boost solving pace\n"
        "• Knowledge problems improve understanding"
    )
    await safe_send_message(update, help_text)

async def get_recommended_problems(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await safe_send_message(update, "Please provide your LeetCode username.\nUsage: /recommended2 <username>")
        return
    
    username = context.args[0]
    user_id = update.effective_user.id
    user_chat_ids.add(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Check if user already has today's problems
    if user_id in user_daily_problems and user_daily_problems[user_id].get('date') == today:
        daily_data = user_daily_problems[user_id]
        await send_existing_problems(update, daily_data)
        return
    
    await update.message.reply_text(f"🎯 Generating personalized problems for {username}...")
    
    # Get user profile
    user_data = await leetcode_service.get_user_profile(username)
    if not user_data:
        await safe_send_message(update, f"❌ User {username} not found or profile is private.")
        return
    
    user_stats = extract_user_stats(user_data)
    user_profiles[user_id] = {'username': username, **user_stats}
    
    # Get personalized problems
    problems = await leetcode_service.get_personalized_problems(user_stats)
    if not problems:
        await safe_send_message(update, "❌ Couldn't generate personalized problems. Please try again.")
        return
    
    # Store today's problems
    user_daily_problems[user_id] = {
        'date': today,
        'username': username,
        'speed_problem': problems['speed_problem'],
        'knowledge_problem': problems['knowledge_problem'],
        'solved_speed': False,
        'solved_knowledge': False
    }
    
    await send_daily_problems(update, problems, username)

async def send_daily_problems(update: Update, problems: Dict[str, Dict[str, Any]], username: str) -> None:
    speed_problem = problems['speed_problem']
    knowledge_problem = problems['knowledge_problem']
    
    message = (
        f"🎯 Daily Problems for {username}\n\n"
        f"⚡ SPEED PROBLEM (Boost your pace)\n"
        f"#{speed_problem.get('frontendQuestionId')} - {speed_problem.get('title')}\n"
        f"Difficulty: {speed_problem.get('difficulty')} | "
        f"Acceptance: {speed_problem.get('acRate', 0):.1f}%\n"
        f"🔗 leetcode.com/problems/{speed_problem.get('titleSlug')}\n\n"
        f"🧠 KNOWLEDGE PROBLEM (Expand your skills)\n"
        f"#{knowledge_problem.get('frontendQuestionId')} - {knowledge_problem.get('title')}\n"
        f"Difficulty: {knowledge_problem.get('difficulty')} | "
        f"Acceptance: {knowledge_problem.get('acRate', 0):.1f}%\n"
        f"🔗 leetcode.com/problems/{knowledge_problem.get('titleSlug')}\n\n"
        f"💡 Use /solved speed or /solved knowledge when done!\n"
        f"📊 Check progress with /mystatus"
    )
    await safe_send_message(update, message)

async def send_existing_problems(update: Update, daily_data: Dict[str, Any]) -> None:
    speed_problem = daily_data['speed_problem']
    knowledge_problem = daily_data['knowledge_problem']
    solved_speed = daily_data['solved_speed']
    solved_knowledge = daily_data['solved_knowledge']
    
    speed_status = "✅ SOLVED" if solved_speed else "⏳ PENDING"
    knowledge_status = "✅ SOLVED" if solved_knowledge else "⏳ PENDING"
    
    message = (
        f"📋 Your Today's Problems ({daily_data['username']})\n\n"
        f"⚡ SPEED PROBLEM - {speed_status}\n"
        f"#{speed_problem.get('frontendQuestionId')} - {speed_problem.get('title')}\n"
        f"🔗 leetcode.com/problems/{speed_problem.get('titleSlug')}\n\n"
        f"🧠 KNOWLEDGE PROBLEM - {knowledge_status}\n"
        f"#{knowledge_problem.get('frontendQuestionId')} - {knowledge_problem.get('title')}\n"
        f"🔗 leetcode.com/problems/{knowledge_problem.get('titleSlug')}\n\n"
    )
    
    if not solved_speed or not solved_knowledge:
        message += "💡 Use /solved speed or /solved knowledge when done!"
    else:
        message += "🎉 Great job! All problems solved for today!"
    
    await safe_send_message(update, message)

async def mark_solved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() not in ['speed', 'knowledge']:
        await safe_send_message(update, "Usage: /solved speed OR /solved knowledge")
        return
    
    user_id = update.effective_user.id
    problem_type = context.args[0].lower()
    
    if user_id not in user_daily_problems:
        await safe_send_message(update, "❌ No daily problems found. Use /recommended2 <username> first!")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    if user_daily_problems[user_id].get('date') != today:
        await safe_send_message(update, "❌ No problems for today. Use /recommended2 <username>!")
        return
    
    # Mark as solved
    if problem_type == 'speed':
        user_daily_problems[user_id]['solved_speed'] = True
        await safe_send_message(update, "⚡ Speed problem marked as solved! Great job! 🎉")
    else:
        user_daily_problems[user_id]['solved_knowledge'] = True
        await safe_send_message(update, "🧠 Knowledge problem marked as solved! Excellent! 🎉")
    
    # Check if both are solved
    daily_data = user_daily_problems[user_id]
    if daily_data['solved_speed'] and daily_data['solved_knowledge']:
        await safe_send_message(update, "🏆 Amazing! You've completed both daily problems! Keep up the great work!")

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_daily_problems:
        await safe_send_message(update, "❌ No daily problems found. Use /recommended2 <username> first!")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    if user_daily_problems[user_id].get('date') != today:
        await safe_send_message(update, "❌ No problems for today. Use /recommended2 <username>!")
        return
    
    await send_existing_problems(update, user_daily_problems[user_id])

async def get_random_problem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎲 Finding a random problem for you...")
    problem = await leetcode_service.get_random_problem()
    if problem:
        await format_and_send_problem(update, problem, "🎲 Random Problem")
    else:
        await safe_send_message(update, "❌ Couldn't fetch a random problem. Please try again.")

async def get_random_easy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🟢 Finding an easy problem for you...")
    problem = await leetcode_service.get_random_problem("Easy")
    if problem:
        await format_and_send_problem(update, problem, "🟢 Easy Problem")
    else:
        await safe_send_message(update, "❌ Couldn't fetch an easy problem.")

async def get_random_medium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🟡 Finding a medium problem for you...")
    problem = await leetcode_service.get_random_problem("Medium")
    if problem:
        await format_and_send_problem(update, problem, "🟡 Medium Problem")
    else:
        await safe_send_message(update, "❌ Couldn't fetch a medium problem.")

async def get_random_hard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔴 Finding a hard problem for you...")
    problem = await leetcode_service.get_random_problem("Hard")
    if problem:
        await format_and_send_problem(update, problem, "🔴 Hard Problem")
    else:
        await safe_send_message(update, "❌ Couldn't fetch a hard problem.")

async def format_and_send_problem(update: Update, problem: Dict[str, Any], header: str) -> None:
    title = problem.get('title', 'Unknown')
    difficulty = problem.get('difficulty', 'Unknown')
    problem_id = problem.get('frontendQuestionId', 'Unknown')
    topics = [tag['name'] for tag in problem.get('topicTags', [])]
    acceptance_rate = problem.get('acRate', 0)
    problem_message = (
        f"{header} #{problem_id}\n\n"
        f"📝 Title: {title}\n"
        f"⚡ Difficulty: {difficulty}\n"
        f"📊 Acceptance Rate: {acceptance_rate:.1f}%\n"
        f"🏷️ Topics: {', '.join(topics[:5])}\n\n"
        f"🔗 leetcode.com/problems/{problem.get('titleSlug', '')}\n\n"
        f"💪 Good luck solving this one!"
    )
    await safe_send_message(update, problem_message)

async def get_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await safe_send_message(update, "Please provide a LeetCode username.\nUsage: /profile <username>")
        return
    username = context.args[0]
    user_chat_ids.add(update.effective_user.id)
    await update.message.reply_text(f"🔍 Analyzing profile for {username}...")
    user_data = await leetcode_service.get_user_profile(username)
    if not user_data:
        await safe_send_message(update, f"❌ User {username} not found or profile is private.")
        return
    
    user_stats = extract_user_stats(user_data)
    user_level = determine_user_level(user_stats['total_solved'], user_stats['easy_solved'], 
                                    user_stats['medium_solved'], user_stats['hard_solved'])
    
    profile_message = (
        f"📊 Profile Analysis: {username}\n\n"
        f"🏆 Statistics:\n"
        f"• Total Solved: {user_stats['total_solved']}\n"
        f"• Easy: {user_stats['easy_solved']} | Medium: {user_stats['medium_solved']} | Hard: {user_stats['hard_solved']}\n"
        f"• Global Ranking: {user_stats['ranking']}\n"
        f"• Skill Level: {user_level}\n\n"
        f"📈 Quick Insights:\n"
        f"• {get_profile_insight(user_stats['total_solved'], user_stats['easy_solved'], user_stats['medium_solved'], user_stats['hard_solved'])}\n\n"
        f"💡 Use /recommended2 {username} for daily problems!"
    )
    await safe_send_message(update, profile_message)

def determine_user_level(total: int, easy: int, medium: int, hard: int) -> str:
    if total < 50:
        return "🌱 Beginner"
    elif total < 150:
        return "📚 Learning"
    elif total < 300:
        return "💪 Intermediate"
    elif total < 500:
        return "🎯 Advanced"
    else:
        return "🏆 Expert"

def get_profile_insight(total: int, easy: int, medium: int, hard: int) -> str:
    if total == 0:
        return "Ready to start your LeetCode journey!"
    elif total < 10:
        return "Great start! Focus on easy problems to build confidence"
    elif easy > medium * 2 and medium > 0:
        return "Focus more on medium problems to level up your skills"
    elif medium > easy and total > 50:
        return "Great balance! Consider adding more hard problems to your practice"
    elif hard > medium and total > 100:
        return "Impressive hard problem solving! You're at an advanced level"
    elif easy + medium + hard != total:
        return "Keep solving problems consistently across all difficulty levels"
    else:
        return "Steady progress across all difficulty levels - keep it up!"

async def generate_study_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await safe_send_message(update, "Please provide a LeetCode username.\nUsage: /plan <username>")
        return
    username = context.args[0]
    user_chat_ids.add(update.effective_user.id)
    await update.message.reply_text(f"🧠 Creating personalized study plan for {username}...")
    user_data = await leetcode_service.get_user_profile(username)
    if not user_data:
        await safe_send_message(update, f"❌ User {username} not found.")
        return
    
    user_stats = extract_user_stats(user_data)
    plan = await gemini_service.generate_personalized_advice(
        user_stats, f"User {username} requested a custom LeetCode study plan."
    )
    plan_message = (
        f"📚 Personalized Study Plan for {username}\n\n"
        f"{plan}\n\n"
        f"🎯 Remember: Consistency beats intensity!\n"
        f"📈 Use /recommended2 {username} for daily practice"
    )
    await safe_send_message(update, plan_message)

async def get_daily_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📅 Fetching today's daily challenge...")
    daily_data = await leetcode_service.get_daily_challenge()
    if not daily_data:
        await safe_send_message(update, "❌ Couldn't fetch today's daily challenge.")
        return
    question = daily_data.get('question', {})
    title = question.get('title', 'Unknown')
    difficulty = question.get('difficulty', 'Unknown')
    topics = [tag['name'] for tag in question.get('topicTags', [])]
    acceptance_rate = question.get('acRate', 0)
    daily_message = (
        f"📅 Today's Daily Challenge\n\n"
        f"🎯 Problem: {title}\n"
        f"⚡ Difficulty: {difficulty}\n"
        f"📊 Acceptance Rate: {acceptance_rate:.1f}%\n"
        f"🏷️ Topics: {', '.join(topics[:5])}\n\n"
        f"💡 Daily challenges give you extra points!\n"
        f"🔗 Solve at: leetcode.com/problems/{question.get('titleSlug', '')}"
    )
    await safe_send_message(update, daily_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.lower().strip()
    user_id = update.effective_user.id
    user_chat_ids.add(user_id)
    responses = {
        'hello': '👋 Hey there! Ready to solve some LeetCode problems?',
        'hi': '👋 Hello! Use /recommended2 <username> for daily problems!',
        'bye': '👋 Goodbye! Keep coding and good luck!',
        'help': 'Use /help to see all available commands!',
        'thanks': '😊 You\'re welcome! Happy coding!',
    }
    response = responses.get(text)
    if response:
        await safe_send_message(update, response)
        logger.info(f"User {user_id} sent: {text}")
    else:
        await safe_send_message(update, 
            "🤔 Try:\n"
            "• /recommended2 <username> - Get daily problems\n"
            "• /help - See all commands\n"
            "• Say 'hello' for a greeting!"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f'Update {update} caused error {context.error}')
    if update and update.message:
        await safe_send_message(update, '⚠️ Something went wrong. Please try again.')

def main() -> None:
    logger.info("Starting Enhanced LeetCode Bot...")
    
    # Validate configuration
    if TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ Please set your bot token! Replace 'YOUR_BOT_TOKEN_HERE' with your actual token.")
        return
    if GEMINI_API_KEY == 'YOUR_GEMINI_API_KEY_HERE':
        logger.error("❌ Please set your Gemini API key! Replace 'YOUR_GEMINI_API_KEY_HERE' with your actual key.")
        return
    
    application = ApplicationBuilder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("recommended2", get_recommended_problems))
    application.add_handler(CommandHandler("solved", mark_solved))
    application.add_handler(CommandHandler("mystatus", check_status))
    application.add_handler(CommandHandler("profile", get_user_profile))
    application.add_handler(CommandHandler("daily", get_daily_challenge))
    application.add_handler(CommandHandler("plan", generate_study_plan))
    application.add_handler(CommandHandler("random", get_random_problem))
    application.add_handler(CommandHandler("easy", get_random_easy))
    application.add_handler(CommandHandler("medium", get_random_medium))
    application.add_handler(CommandHandler("hard", get_random_hard))

    # Register message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Register error handler
    application.add_error_handler(error_handler)

    logger.info("Enhanced LeetCode Bot started successfully! 🚀")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
