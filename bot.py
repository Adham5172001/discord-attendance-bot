import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import statistics
import asyncio
import re

# Configure logging for cloud deployment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Cloud platforms capture stdout
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration - DISABLE built-in help command to avoid conflicts
intents = discord.Intents.default()
intents.voice_states = True  # Required to track voice channel events
intents.message_content = True  # Required for commands

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)  # Disable built-in help

# Data storage file
ATTENDANCE_FILE = 'attendance_data.json'

# Attendance tracking functions
def load_attendance_data():
    """Load attendance data from JSON file"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            with open(ATTENDANCE_FILE, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded attendance data for {len(data)} guilds")
                return data
        logger.info("No existing attendance data found, starting fresh")
        return {}
    except Exception as e:
        logger.error(f"Error loading attendance data: {e}")
        return {}

def save_attendance_data(data):
    """Save attendance data to JSON file"""
    try:
        with open(ATTENDANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug("Attendance data saved successfully")
    except Exception as e:
        logger.error(f"Error saving attendance data: {e}")

def format_timestamp(iso_timestamp):
    """Convert ISO timestamp to user-friendly format"""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime('%B %d, %Y at %I:%M:%S %p')
    except:
        return iso_timestamp

def format_duration(duration_str):
    """Convert duration string to user-friendly format"""
    try:
        if duration_str == "Ongoing" or duration_str is None:
            return "Ongoing"
        
        # Parse the duration string (format: H:MM:SS.microseconds)
        parts = duration_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        
        if hours > 0:
            return f"{hours}h {minutes}m {int(seconds)}s"
        elif minutes > 0:
            return f"{minutes}m {int(seconds)}s"
        else:
            return f"{int(seconds)}s"
    except:
        return duration_str

# Global attendance data
attendance_data = load_attendance_data()

@bot.event
async def on_ready():
    """Event triggered when bot is ready"""
    # Set bot status to invisible
    await bot.change_presence(status=discord.Status.invisible)
    
    logger.info(f'{bot.user} has connected to Discord in INVISIBLE mode!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')
    logger.info('Bot is running invisibly - users cannot see it online')
    logger.info('🎵 Music functionality temporarily disabled due to cloud restrictions')
    logger.info('📊 Attendance tracking fully operational!')
    
    # Log guild information
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id})')

@bot.event
async def on_voice_state_update(member, before, after):
    """Event triggered when a user's voice state changes"""
    try:
        guild_id = str(member.guild.id)
        user_id = str(member.id)
        timestamp = datetime.now().isoformat()
        
        # Initialize guild data if not exists
        if guild_id not in attendance_data:
            attendance_data[guild_id] = {}
        
        # Initialize user data if not exists
        if user_id not in attendance_data[guild_id]:
            attendance_data[guild_id][user_id] = {
                'username': str(member),
                'display_name': member.display_name,
                'sessions': []
            }
        
        # User joined a voice channel
        if before.channel is None and after.channel is not None:
            session_data = {
                'channel_name': after.channel.name,
                'channel_id': str(after.channel.id),
                'join_time': timestamp,
                'leave_time': None,
                'duration': None
            }
            attendance_data[guild_id][user_id]['sessions'].append(session_data)
            logger.info(f"{member.display_name} joined {after.channel.name} in {member.guild.name}")
        
        # User left a voice channel
        elif before.channel is not None and after.channel is None:
            # Find the most recent session without a leave time
            user_sessions = attendance_data[guild_id][user_id]['sessions']
            for session in reversed(user_sessions):
                if session['leave_time'] is None and session['channel_id'] == str(before.channel.id):
                    session['leave_time'] = timestamp
                    # Calculate duration
                    join_time = datetime.fromisoformat(session['join_time'])
                    leave_time = datetime.fromisoformat(timestamp)
                    duration = leave_time - join_time
                    session['duration'] = str(duration)
                    break
            logger.info(f"{member.display_name} left {before.channel.name} in {member.guild.name}")
        
        # User switched channels
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            # End session in previous channel
            user_sessions = attendance_data[guild_id][user_id]['sessions']
            for session in reversed(user_sessions):
                if session['leave_time'] is None and session['channel_id'] == str(before.channel.id):
                    session['leave_time'] = timestamp
                    join_time = datetime.fromisoformat(session['join_time'])
                    leave_time = datetime.fromisoformat(timestamp)
                    duration = leave_time - join_time
                    session['duration'] = str(duration)
                    break
            
            # Start new session in new channel
            session_data = {
                'channel_name': after.channel.name,
                'channel_id': str(after.channel.id),
                'join_time': timestamp,
                'leave_time': None,
                'duration': None
            }
            attendance_data[guild_id][user_id]['sessions'].append(session_data)
            logger.info(f"{member.display_name} switched from {before.channel.name} to {after.channel.name} in {member.guild.name}")
        
        # Save data after each update
        save_attendance_data(attendance_data)
        
    except Exception as e:
        logger.error(f"Error in voice state update: {e}")

# Music Commands (Simplified for cloud compatibility)
@bot.command(name='play', aliases=['p'])
async def play_music(ctx, *, query):
    """Explain music limitations on free cloud hosting"""
    embed = discord.Embed(
        title="🎵 Music Feature Status",
        description="**Music functionality is currently limited on free cloud hosting platforms.**",
        color=0xffaa00
    )
    
    embed.add_field(
        name="🚫 Current Limitations",
        value="• Free cloud platforms block YouTube downloading\n"
              "• Network restrictions prevent audio streaming\n"
              "• Voice channel connections are unstable\n"
              "• SSL/TLS policies block media access",
        inline=False
    )
    
    embed.add_field(
        name="✅ What's Working",
        value="• Voice channel detection\n"
              "• Command processing\n"
              "• Attendance tracking\n"
              "• All other bot features",
        inline=False
    )
    
    embed.add_field(
        name="🔧 Solutions",
        value="**For Full Music Functionality:**\n"
              "• Use a paid cloud service (Heroku, DigitalOcean)\n"
              "• Run bot on your local machine\n"
              "• Use a VPS with fewer restrictions\n\n"
              "**Current Focus:**\n"
              "• Attendance tracking works perfectly ✅\n"
              "• All other features operational ✅",
        inline=False
    )
    
    embed.set_footer(text="🔇 Invisible Attendance Bot | Cloud-Optimized ☁️")
    await ctx.send(embed=embed)

@bot.command(name='music_info')
async def music_info(ctx):
    """Detailed explanation of music limitations"""
    embed = discord.Embed(
        title="🎵 Music Bot Limitations on Free Cloud Hosting",
        description="Here's why music bots struggle on free cloud platforms:",
        color=0x0099ff
    )
    
    embed.add_field(
        name="🌐 Network Restrictions",
        value="• Railway/Render block YouTube API access\n"
              "• SSL certificate policies prevent downloads\n"
              "• Bandwidth limitations for audio streaming\n"
              "• Firewall rules block media connections",
        inline=False
    )
    
    embed.add_field(
        name="💰 Why Premium Hosting Works",
        value="• Dedicated IP addresses\n"
              "• Relaxed network policies\n"
              "• Higher bandwidth allowances\n"
              "• Custom SSL configurations\n"
              "• VPN/proxy capabilities",
        inline=False
    )
    
    embed.add_field(
        name="🏠 Local Hosting Benefits",
        value="• No network restrictions\n"
              "• Direct YouTube access\n"
              "• Full control over connections\n"
              "• Unlimited bandwidth\n"
              "• Custom configurations",
        inline=False
    )
    
    embed.add_field(
        name="📊 What Works Perfectly",
        value="• **Attendance Tracking** - 100% functional ✅\n"
              "• **Voice Channel Monitoring** - Real-time ✅\n"
              "• **Data Analytics** - Complete stats ✅\n"
              "• **User Management** - Full features ✅\n"
              "• **Cloud Operation** - 24/7 uptime ✅",
        inline=False
    )
    
    embed.set_footer(text="🔇 Invisible Attendance Bot | Specialized for Voice Tracking ☁️")
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """Check if bot is responsive"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"🔇 **Invisible Attendance Bot** running on cloud ☁️\n\n"
                   f"**Latency:** {latency}ms\n"
                   f"**Status:** Invisible Mode 👻\n"
                   f"**Attendance Tracking:** ✅ Fully Operational\n"
                   f"**Music:** ⚠️ Limited by cloud restrictions",
        color=0x00ff00
    )
    embed.set_footer(text="🔇 Specialized for Voice Channel Attendance Tracking")
    await ctx.send(embed=embed)

@bot.command(name='status')
async def bot_status(ctx):
    """Show bot status and capabilities"""
    embed = discord.Embed(
        title="🤖 Bot Status & Capabilities",
        description="**Current Mode:** Invisible 👻\n**Primary Function:** Voice Channel Attendance Tracking",
        color=0x808080
    )
    
    embed.add_field(
        name="✅ Fully Operational Features",
        value="• **Voice Channel Monitoring** - Real-time tracking\n"
              "• **Attendance Analytics** - Detailed statistics\n"
              "• **User Session Tracking** - Join/leave times\n"
              "• **Data Persistence** - Cloud storage\n"
              "• **Invisible Operation** - Hidden from users\n"
              "• **24/7 Cloud Hosting** - Always online",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Limited Features",
        value="• **Music Playback** - Restricted by cloud platform\n"
              "• **Audio Streaming** - Network limitations\n"
              "• **YouTube Downloads** - Blocked by hosting provider",
        inline=False
    )
    
    embed.add_field(
        name="🎯 Specialized Capabilities",
        value="• **Professional Attendance System** 📊\n"
              "• **Advanced Analytics** 📈\n"
              "• **User Behavior Tracking** 👥\n"
              "• **Session Management** ⏱️\n"
              "• **Data Export** 📁",
        inline=False
    )
    
    embed.set_footer(text="🔇 Invisible Attendance Bot | Cloud-Optimized for Voice Tracking ☁️")
    await ctx.send(embed=embed)

@bot.command(name='commands', aliases=['help'])
async def show_commands(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="🔇 Invisible Attendance Bot Commands",
        description="**Specialized for Voice Channel Attendance Tracking**\n\n"
                   "Your bot is running in **INVISIBLE mode** 👻 and optimized for **attendance monitoring**!",
        color=0x0099ff
    )
    
    # Attendance commands (fully functional)
    embed.add_field(
        name="📊 Attendance Tracking (✅ Fully Functional)",
        value="`!attendance` - Show server attendance summary\n"
              "`!attendance @user` - Show detailed user attendance\n"
              "`!export` - Export attendance data to CSV\n"
              "`!stats` - Show detailed server statistics\n"
              "`!clear_data` - Clear all attendance data (Admin only)",
        inline=False
    )
    
    # Bot status commands
    embed.add_field(
        name="🤖 Bot Status & Info",
        value="`!ping` - Check bot responsiveness\n"
              "`!status` - Show bot capabilities\n"
              "`!commands` - Show this help message\n"
              "`!music_info` - Explain music limitations",
        inline=False
    )
    
    # Music commands (limited)
    embed.add_field(
        name="🎵 Music Commands (⚠️ Limited by Cloud)",
        value="`!play <song>` - Explain music limitations\n"
              "`!music_info` - Detailed music explanation\n\n"
              "**Note:** Music is limited on free cloud hosting.\n"
              "Attendance tracking works perfectly! 📊",
        inline=False
    )
    
    embed.set_footer(text="🔇 Invisible Attendance Bot | Optimized for Voice Channel Monitoring ☁️")
    await ctx.send(embed=embed)

@bot.command(name='attendance')
async def show_attendance(ctx, user_mention=None):
    """Show attendance data for a user or all users"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id not in attendance_data:
            embed = discord.Embed(
                title="📊 Attendance Data",
                description="No attendance data found for this server yet.\n\n"
                           "**The bot will start tracking when users join voice channels!**",
                color=0x808080
            )
            embed.set_footer(text="🔇 Invisible Attendance Bot | Voice Channel Monitoring ☁️")
            await ctx.send(embed=embed)
            return
        
        if user_mention:
            # Show data for specific user
            try:
                user_id = user_mention.strip('<@!>')
                if user_id in attendance_data[guild_id]:
                    user_data = attendance_data[guild_id][user_id]
                    stats = get_session_stats(user_data['sessions'])
                    
                    embed = discord.Embed(
                        title=f"📊 Attendance Report for {user_data.get('display_name', user_data['username'])}", 
                        color=0x00ff00,
                        timestamp=datetime.now()
                    )
                    
                    # Add statistics
                    embed.add_field(
                        name="📈 Session Statistics",
                        value=f"**Total Sessions:** {stats['total_sessions']}\n"
                              f"**Completed Sessions:** {stats['completed_sessions']}\n"
                              f"**Currently Active:** {stats['active_sessions']}\n"
                              f"**Total Time:** {stats['total_time']}\n"
                              f"**Average Session:** {stats['avg_session']}\n"
                              f"**Longest Session:** {stats['longest_session']}",
                        inline=False
                    )
                    
                    # Show recent sessions
                    if user_data['sessions']:
                        recent_sessions = user_data['sessions'][-5:]  # Last 5 sessions
                        session_text = ""
                        for session in recent_sessions:
                            join_time = format_timestamp(session['join_time'])
                            duration = format_duration(session.get('duration', 'Ongoing'))
                            session_text += f"**{session['channel_name']}**\n{join_time}\nDuration: {duration}\n\n"
                        
                        embed.add_field(
                            name="🕒 Recent Sessions",
                            value=session_text[:1024],  # Discord field limit
                            inline=False
                        )
                    
                    embed.set_footer(text="🔇 Invisible Attendance Bot | Voice Channel Monitoring ☁️")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ No attendance data found for this user.")
            except Exception as e:
                logger.error(f"Error showing user attendance: {e}")
                await ctx.send("❌ Invalid user mention. Use @username format.")
        else:
            # Show summary for all users
            embed = discord.Embed(
                title="📊 Server Attendance Summary", 
                color=0x0099ff,
                timestamp=datetime.now()
            )
            
            total_users = len(attendance_data[guild_id])
            total_sessions = sum(len(user_data['sessions']) for user_data in attendance_data[guild_id].values())
            currently_active = sum(
                sum(1 for session in user_data['sessions'] if session.get('leave_time') is None)
                for user_data in attendance_data[guild_id].values()
            )
            
            embed.add_field(
                name="📈 Server Statistics",
                value=f"**Total Users Tracked:** {total_users}\n"
                      f"**Total Sessions:** {total_sessions}\n"
                      f"**Currently Active:** {currently_active}",
                inline=False
            )
            
            # Show most active users
            user_stats = []
            for user_id, user_data in attendance_data[guild_id].items():
                stats = get_session_stats(user_data['sessions'])
                user_stats.append({
                    'name': user_data.get('display_name', user_data['username']),
                    'sessions': stats['total_sessions'],
                    'total_time': stats['total_time']
                })
            
            # Sort by session count
            user_stats.sort(key=lambda x: x['sessions'], reverse=True)
            
            if user_stats:
                top_users = user_stats[:5]  # Top 5 users
                top_users_text = ""
                for i, user in enumerate(top_users, 1):
                    top_users_text += f"{i}. **{user['name']}** - {user['sessions']} sessions ({user['total_time']})\n"
                
                embed.add_field(
                    name="🏆 Most Active Users",
                    value=top_users_text,
                    inline=False
                )
            
            embed.set_footer(text="🔇 Invisible Attendance Bot | Voice Channel Monitoring ☁️")
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in attendance command: {e}")
        await ctx.send("❌ An error occurred while fetching attendance data.")

@bot.command(name='export')
async def export_attendance(ctx):
    """Export attendance data to CSV format"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id not in attendance_data or not attendance_data[guild_id]:
            await ctx.send("❌ No attendance data to export.")
            return
        
        # Create CSV content
        csv_content = "Username,Display Name,Channel,Join Time,Leave Time,Duration\n"
        
        for user_id, user_data in attendance_data[guild_id].items():
            username = user_data['username']
            display_name = user_data.get('display_name', username)
            
            for session in user_data['sessions']:
                join_time = format_timestamp(session['join_time'])
                leave_time = format_timestamp(session.get('leave_time', 'Ongoing'))
                duration = format_duration(session.get('duration', 'Ongoing'))
                channel = session['channel_name']
                
                csv_content += f'"{username}","{display_name}","{channel}","{join_time}","{leave_time}","{duration}"\n'
        
        # Save to file
        filename = f"attendance_export_{ctx.guild.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Send file
        embed = discord.Embed(
            title="📁 Attendance Data Export",
            description=f"**Server:** {ctx.guild.name}\n"
                       f"**Export Time:** {datetime.now().strftime('%B %d, %Y at %I:%M:%S %p')}\n"
                       f"**Total Users:** {len(attendance_data[guild_id])}\n"
                       f"**File Format:** CSV",
            color=0x00ff00
        )
        embed.set_footer(text="🔇 Invisible Attendance Bot | Data Export ☁️")
        
        await ctx.send(embed=embed, file=discord.File(filename))
        
        # Clean up file
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error exporting attendance data: {e}")
        await ctx.send("❌ An error occurred while exporting data.")

def get_session_stats(sessions):
    """Get statistics about user sessions"""
    if not sessions:
        return {
            "total_sessions": 0, 
            "completed_sessions": 0,
            "active_sessions": 0,
            "total_time": "0s", 
            "avg_session": "0s", 
            "longest_session": "0s"
        }
    
    completed_sessions = [s for s in sessions if s.get('duration') and s['duration'] != "Ongoing"]
    active_sessions = sum(1 for s in sessions if s.get('leave_time') is None)
    durations = []
    
    for session in completed_sessions:
        try:
            parts = session['duration'].split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            total_seconds = hours * 3600 + minutes * 60 + seconds
            durations.append(total_seconds)
        except:
            continue
    
    total_time = calculate_total_time(sessions)
    avg_session = "0s"
    longest_session = "0s"
    
    if durations:
        avg_seconds = statistics.mean(durations)
        max_seconds = max(durations)
        
        # Format average
        avg_h = int(avg_seconds // 3600)
        avg_m = int((avg_seconds % 3600) // 60)
        avg_s = int(avg_seconds % 60)
        if avg_h > 0:
            avg_session = f"{avg_h}h {avg_m}m {avg_s}s"
        elif avg_m > 0:
            avg_session = f"{avg_m}m {avg_s}s"
        else:
            avg_session = f"{avg_s}s"
        
        # Format longest
        max_h = int(max_seconds // 3600)
        max_m = int((max_seconds % 3600) // 60)
        max_s = int(max_seconds % 60)
        if max_h > 0:
            longest_session = f"{max_h}h {max_m}m {max_s}s"
        elif max_m > 0:
            longest_session = f"{max_m}m {max_s}s"
        else:
            longest_session = f"{max_s}s"
    
    return {
        "total_sessions": len(sessions),
        "completed_sessions": len(completed_sessions),
        "active_sessions": active_sessions,
        "total_time": total_time,
        "avg_session": avg_session,
        "longest_session": longest_session
    }

def calculate_total_time(sessions):
    """Calculate total time spent across all sessions"""
    total_seconds = 0
    for session in sessions:
        if session.get('duration') and session['duration'] != "Ongoing":
            try:
                parts = session['duration'].split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                total_seconds += hours * 3600 + minutes * 60 + seconds
            except:
                continue
    
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!commands` to see available commands.")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {error}")

# Run the bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        logger.error("Please set the DISCORD_BOT_TOKEN environment variable")
        exit(1)
    else:
        logger.info("Starting Cloud-Compatible Invisible Discord Attendance Bot...")
        logger.info("Bot optimized for voice channel attendance tracking")
        logger.info("Music functionality disabled due to cloud platform restrictions")
        logger.info("Bot will run 24/7 on cloud infrastructure in INVISIBLE mode")
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            exit(1)
