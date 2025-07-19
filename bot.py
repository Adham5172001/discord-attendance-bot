import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import statistics

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

# Bot configuration
intents = discord.Intents.default()
intents.voice_states = True  # Required to track voice channel events
intents.message_content = True  # Required for commands

bot = commands.Bot(command_prefix='!', intents=intents)

# Data storage file
ATTENDANCE_FILE = 'attendance_data.json'

# Initialize attendance data structure
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

def get_session_stats(sessions):
    """Get statistics about user sessions"""
    if not sessions:
        return {"total_sessions": 0, "total_time": "0s", "avg_session": "0s", "longest_session": "0s"}
    
    completed_sessions = [s for s in sessions if s.get('duration') and s['duration'] != "Ongoing"]
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
    
    active_sessions = sum(1 for s in sessions if s.get('leave_time') is None)
    
    return {
        "total_sessions": len(sessions),
        "completed_sessions": len(completed_sessions),
        "active_sessions": active_sessions,
        "total_time": total_time,
        "avg_session": avg_session,
        "longest_session": longest_session
    }

# Global attendance data
attendance_data = load_attendance_data()

@bot.event
async def on_ready():
    """Event triggered when bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')
    
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

@bot.command(name='attendance')
async def show_attendance(ctx, user_mention=None):
    """Show attendance data for a user or all users"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id not in attendance_data:
            await ctx.send("No attendance data found for this server.")
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
                        name="📈 Statistics",
                        value=f"**Total Sessions:** {stats['total_sessions']}\n"
                              f"**Completed Sessions:** {stats['completed_sessions']}\n"
                              f"**Currently Active:** {stats['active_sessions']}\n"
                              f"**Total Time:** {stats['total_time']}\n"
                              f"**Average Session:** {stats['avg_session']}\n"
                              f"**Longest Session:** {stats['longest_session']}",
                        inline=False
                    )
                    
                    # Show recent sessions
                    recent_sessions = user_data['sessions'][-5:]  # Last 5 sessions
                    if recent_sessions:
                        embed.add_field(
                            name="🕒 Recent Sessions",
                            value="_ _",  # Empty value for spacing
                            inline=False
                        )
                        
                        for i, session in enumerate(recent_sessions, 1):
                            join_time = format_timestamp(session['join_time'])
                            leave_time = session['leave_time']
                            if leave_time:
                                leave_time = format_timestamp(leave_time)
                                duration = format_duration(session['duration'])
                                status = "✅ Completed"
                            else:
                                leave_time = "Still in channel"
                                duration = "Ongoing"
                                status = "🔴 Active"
                            
                            embed.add_field(
                                name=f"{status} - {session['channel_name']}",
                                value=f"**Joined:** {join_time}\n**Left:** {leave_time}\n**Duration:** {duration}",
                                inline=True
                            )
                    
                    embed.set_footer(text=f"Requested by {ctx.author.display_name} | Running on Cloud ☁️")
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
            
            # Top users by session count
            user_stats = []
            for user_id, user_data in attendance_data[guild_id].items():
                stats = get_session_stats(user_data['sessions'])
                user_stats.append({
                    'name': user_data.get('display_name', user_data['username']),
                    'sessions': stats['total_sessions'],
                    'total_time': stats['total_time'],
                    'active': stats['active_sessions']
                })
            
            # Sort by session count
            user_stats.sort(key=lambda x: x['sessions'], reverse=True)
            
            if user_stats:
                top_users = user_stats[:10]  # Top 10 users
                user_list = ""
                for i, user in enumerate(top_users, 1):
                    status = "🔴" if user['active'] > 0 else "⚪"
                    user_list += f"{i}. {status} **{user['name']}**\n"
                    user_list += f"   Sessions: {user['sessions']} | Total Time: {user['total_time']}\n\n"
                
                embed.add_field(
                    name="👥 Top Users by Activity",
                    value=user_list[:1024],  # Discord field limit
                    inline=False
                )
            
            embed.set_footer(text=f"Use !attendance @user for detailed reports | Running on Cloud ☁️")
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in attendance command: {e}")
        await ctx.send("❌ An error occurred while fetching attendance data.")

@bot.command(name='stats')
async def show_detailed_stats(ctx, user_mention=None):
    """Show detailed statistics and analytics"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id not in attendance_data:
            await ctx.send("No attendance data found for this server.")
            return
        
        if user_mention:
            # Detailed user stats
            try:
                user_id = user_mention.strip('<@!>')
                if user_id in attendance_data[guild_id]:
                    user_data = attendance_data[guild_id][user_id]
                    sessions = user_data['sessions']
                    
                    embed = discord.Embed(
                        title=f"📈 Detailed Analytics for {user_data.get('display_name', user_data['username'])}", 
                        color=0xff6b35,
                        timestamp=datetime.now()
                    )
                    
                    # Channel breakdown
                    channel_stats = {}
                    for session in sessions:
                        channel = session['channel_name']
                        if channel not in channel_stats:
                            channel_stats[channel] = {'count': 0, 'total_time': 0}
                        channel_stats[channel]['count'] += 1
                        
                        if session.get('duration') and session['duration'] != "Ongoing":
                            try:
                                parts = session['duration'].split(':')
                                hours = int(parts[0])
                                minutes = int(parts[1])
                                seconds = float(parts[2])
                                channel_stats[channel]['total_time'] += hours * 3600 + minutes * 60 + seconds
                            except:
                                continue
                    
                    if channel_stats:
                        channel_breakdown = ""
                        for channel, stats in sorted(channel_stats.items(), key=lambda x: x[1]['count'], reverse=True):
                            total_seconds = stats['total_time']
                            hours = int(total_seconds // 3600)
                            minutes = int((total_seconds % 3600) // 60)
                            seconds = int(total_seconds % 60)
                            
                            if hours > 0:
                                time_str = f"{hours}h {minutes}m"
                            elif minutes > 0:
                                time_str = f"{minutes}m {seconds}s"
                            else:
                                time_str = f"{seconds}s"
                            
                            channel_breakdown += f"**{channel}:** {stats['count']} sessions, {time_str}\n"
                        
                        embed.add_field(
                            name="📍 Channel Breakdown",
                            value=channel_breakdown[:1024],
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Running on Cloud ☁️")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ No attendance data found for this user.")
            except Exception as e:
                logger.error(f"Error showing user stats: {e}")
                await ctx.send("❌ Invalid user mention. Use @username format.")
        else:
            # Server-wide detailed stats
            embed = discord.Embed(
                title="📈 Detailed Server Analytics", 
                color=0xff6b35,
                timestamp=datetime.now()
            )
            
            # Channel popularity
            all_channel_stats = {}
            for user_data in attendance_data[guild_id].values():
                for session in user_data['sessions']:
                    channel = session['channel_name']
                    if channel not in all_channel_stats:
                        all_channel_stats[channel] = {'sessions': 0, 'unique_users': set()}
                    all_channel_stats[channel]['sessions'] += 1
                    all_channel_stats[channel]['unique_users'].add(user_data['username'])
            
            if all_channel_stats:
                channel_popularity = ""
                for channel, stats in sorted(all_channel_stats.items(), key=lambda x: x[1]['sessions'], reverse=True):
                    unique_users = len(stats['unique_users'])
                    channel_popularity += f"**{channel}:** {stats['sessions']} sessions, {unique_users} users\n"
                
                embed.add_field(
                    name="📍 Channel Popularity",
                    value=channel_popularity[:1024],
                    inline=False
                )
            
            embed.set_footer(text=f"Running on Cloud ☁️")
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await ctx.send("❌ An error occurred while fetching statistics.")

@bot.command(name='export')
async def export_attendance(ctx, format_type="csv"):
    """Export attendance data to CSV or detailed format"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id not in attendance_data:
            await ctx.send("No attendance data found for this server.")
            return
        
        if format_type.lower() == "detailed":
            # Create detailed JSON export
            export_data = {}
            for user_id, user_data in attendance_data[guild_id].items():
                stats = get_session_stats(user_data['sessions'])
                formatted_sessions = []
                
                for session in user_data['sessions']:
                    formatted_session = {
                        'channel_name': session['channel_name'],
                        'join_time': format_timestamp(session['join_time']),
                        'leave_time': format_timestamp(session['leave_time']) if session['leave_time'] else "Still in channel",
                        'duration': format_duration(session['duration']) if session['duration'] else "Ongoing"
                    }
                    formatted_sessions.append(formatted_session)
                
                export_data[user_data.get('display_name', user_data['username'])] = {
                    'statistics': stats,
                    'sessions': formatted_sessions
                }
            
            filename = f"detailed_attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            await ctx.send("📊 Detailed attendance data exported!", file=discord.File(filename))
            os.remove(filename)
        else:
            # Create CSV content with better formatting
            csv_content = "Username,Display Name,Channel,Join Time,Leave Time,Duration,Status\n"
            
            for user_id, user_data in attendance_data[guild_id].items():
                for session in user_data['sessions']:
                    join_time = format_timestamp(session['join_time'])
                    leave_time = format_timestamp(session['leave_time']) if session['leave_time'] else "Still in channel"
                    duration = format_duration(session['duration']) if session['duration'] else "Ongoing"
                    status = "Completed" if session['leave_time'] else "Active"
                    
                    csv_content += f'"{user_data["username"]}","{user_data.get("display_name", user_data["username"])}","{session["channel_name"]}","{join_time}","{leave_time}","{duration}","{status}"\n'
            
            # Save to file and send
            filename = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, 'w') as f:
                f.write(csv_content)
            
            await ctx.send("📊 Attendance data exported to CSV!", file=discord.File(filename))
            os.remove(filename)
            
    except Exception as e:
        logger.error(f"Error in export command: {e}")
        await ctx.send("❌ An error occurred while exporting data.")

@bot.command(name='clear_data')
@commands.has_permissions(administrator=True)
async def clear_attendance_data(ctx):
    """Clear all attendance data (Admin only)"""
    try:
        guild_id = str(ctx.guild.id)
        
        if guild_id in attendance_data:
            del attendance_data[guild_id]
            save_attendance_data(attendance_data)
            logger.info(f"Attendance data cleared for guild {ctx.guild.name}")
            await ctx.send("✅ All attendance data has been cleared.")
        else:
            await ctx.send("❌ No attendance data found to clear.")
            
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        await ctx.send("❌ An error occurred while clearing data.")

@bot.command(name='ping')
async def ping(ctx):
    """Check if bot is responsive"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot is running on cloud ☁️\nLatency: {latency}ms",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!help` to see available commands.")
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
        logger.info("Starting Discord Attendance Bot...")
        logger.info("Bot will run 24/7 on cloud infrastructure")
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            exit(1)

