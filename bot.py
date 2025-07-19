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
import aiohttp
from collections import deque
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import random

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

# Music configuration
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractaudio': True,
    'audioformat': 'mp3',
    'audioquality': 192,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# Initialize Spotify client (optional - requires API keys)
spotify = None
try:
    spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if spotify_client_id and spotify_client_secret:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret
        ))
        logger.info("Spotify integration enabled")
    else:
        logger.info("Spotify credentials not found - Spotify features disabled")
except Exception as e:
    logger.warning(f"Failed to initialize Spotify client: {e}")

# Music queue and player management
music_queues = {}
voice_clients = {}

class MusicSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
                
                if 'entries' in data:
                    # Take first item from a playlist
                    data = data['entries'][0]
                
                filename = data['url'] if stream else ytdl.prepare_filename(data)
                return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)
            except Exception as e:
                logger.error(f"Error extracting audio from {url}: {e}")
                raise

class AdvancedMusicQueue:
    def __init__(self):
        self.queue = deque()
        self.history = deque(maxlen=50)  # Keep last 50 played songs
        self.current = None
        self.loop_mode = "off"  # off, song, queue
        self.shuffle = False
        self.volume = 0.5
        self.autoplay = False
        self.original_queue = deque()  # For shuffle mode

    def add(self, song):
        self.queue.append(song)
        if self.shuffle and not self.original_queue:
            self.original_queue = self.queue.copy()

    def add_multiple(self, songs):
        for song in songs:
            self.add(song)

    def next(self):
        if self.loop_mode == "song" and self.current:
            return self.current
        
        if self.current:
            self.history.append(self.current)
        
        if self.loop_mode == "queue" and not self.queue and self.history:
            # Restart queue from history
            self.queue = deque(self.history)
            self.history.clear()
        
        if self.queue:
            if self.shuffle:
                # Pick random song from queue
                queue_list = list(self.queue)
                random_song = random.choice(queue_list)
                self.queue.remove(random_song)
                self.current = random_song
            else:
                self.current = self.queue.popleft()
            return self.current
        return None

    def skip(self):
        if self.queue:
            if self.shuffle:
                queue_list = list(self.queue)
                random_song = random.choice(queue_list)
                self.queue.remove(random_song)
                self.current = random_song
            else:
                self.current = self.queue.popleft()
            return self.current
        return None

    def clear(self):
        self.queue.clear()
        self.history.clear()
        self.original_queue.clear()
        self.current = None

    def remove(self, index):
        if 0 <= index < len(self.queue):
            queue_list = list(self.queue)
            removed = queue_list.pop(index)
            self.queue = deque(queue_list)
            return removed
        return None

    def move(self, from_index, to_index):
        if 0 <= from_index < len(self.queue) and 0 <= to_index < len(self.queue):
            queue_list = list(self.queue)
            song = queue_list.pop(from_index)
            queue_list.insert(to_index, song)
            self.queue = deque(queue_list)
            return True
        return False

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        if self.shuffle:
            # Store original order
            self.original_queue = self.queue.copy()
            # Shuffle current queue
            queue_list = list(self.queue)
            random.shuffle(queue_list)
            self.queue = deque(queue_list)
        else:
            # Restore original order if available
            if self.original_queue:
                self.queue = self.original_queue.copy()
                self.original_queue.clear()
        return self.shuffle

    def set_loop_mode(self, mode):
        valid_modes = ["off", "song", "queue"]
        if mode in valid_modes:
            self.loop_mode = mode
            return True
        return False

# Attendance tracking functions (keeping existing functionality)
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

def format_music_duration(seconds):
    """Format music duration in seconds to readable format"""
    if not seconds:
        return "Unknown"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

async def get_spotify_track_info(url):
    """Extract track info from Spotify URL"""
    if not spotify:
        return None
    
    try:
        # Extract track ID from Spotify URL
        track_id = re.search(r'track/([a-zA-Z0-9]+)', url)
        if not track_id:
            return None
        
        track = spotify.track(track_id.group(1))
        
        # Create search query for YouTube
        search_query = f"{track['artists'][0]['name']} {track['name']}"
        
        return {
            'title': track['name'],
            'artist': track['artists'][0]['name'],
            'search_query': search_query,
            'duration': track['duration_ms'] // 1000,
            'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'spotify_url': url
        }
    except Exception as e:
        logger.error(f"Error getting Spotify track info: {e}")
        return None

async def get_spotify_playlist_info(url):
    """Extract playlist info from Spotify URL"""
    if not spotify:
        return None
    
    try:
        # Extract playlist ID from Spotify URL
        playlist_id = re.search(r'playlist/([a-zA-Z0-9]+)', url)
        if not playlist_id:
            return None
        
        playlist = spotify.playlist(playlist_id.group(1))
        tracks = []
        
        for item in playlist['tracks']['items'][:50]:  # Limit to 50 tracks
            if item['track']:
                track = item['track']
                search_query = f"{track['artists'][0]['name']} {track['name']}"
                tracks.append({
                    'title': track['name'],
                    'artist': track['artists'][0]['name'],
                    'search_query': search_query,
                    'duration': track['duration_ms'] // 1000,
                    'spotify_url': track['external_urls']['spotify']
                })
        
        return {
            'name': playlist['name'],
            'tracks': tracks,
            'total_tracks': len(tracks)
        }
    except Exception as e:
        logger.error(f"Error getting Spotify playlist info: {e}")
        return None

def is_url(string):
    """Check if string is a URL"""
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(string) is not None

# Global attendance data
attendance_data = load_attendance_data()

@bot.event
async def on_ready():
    """Event triggered when bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')
    logger.info('Advanced Music functionality enabled! 🎵')
    
    # Log guild information
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id})')
        # Initialize music queue for each guild
        if guild.id not in music_queues:
            music_queues[guild.id] = AdvancedMusicQueue()

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

# Advanced Music Commands
@bot.command(name='play', aliases=['p'])
async def play_music(ctx, *, query):
    """Play music from YouTube or Spotify"""
    try:
        # Check if user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to play music!")
            return
        
        channel = ctx.author.voice.channel
        guild_id = ctx.guild.id
        
        # Initialize music queue if not exists
        if guild_id not in music_queues:
            music_queues[guild_id] = AdvancedMusicQueue()
        
        # Connect to voice channel if not already connected
        if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
            voice_clients[guild_id] = await channel.connect()
            logger.info(f"Connected to voice channel: {channel.name}")
        
        # Handle Spotify playlists
        if 'spotify.com/playlist' in query:
            playlist_info = await get_spotify_playlist_info(query)
            if playlist_info:
                embed = discord.Embed(
                    title="🎵 Adding Spotify Playlist",
                    description=f"**{playlist_info['name']}**\nAdding {playlist_info['total_tracks']} tracks to queue...",
                    color=0x1DB954
                )
                loading_msg = await ctx.send(embed=embed)
                
                added_count = 0
                for track in playlist_info['tracks']:
                    try:
                        search_query = f"ytsearch:{track['search_query']}"
                        source = await MusicSource.from_url(search_query, loop=bot.loop, stream=True)
                        
                        music_queues[guild_id].add({
                            'source': source,
                            'title': source.title,
                            'url': source.url,
                            'duration': source.duration,
                            'thumbnail': source.thumbnail,
                            'uploader': source.uploader,
                            'requester': ctx.author
                        })
                        added_count += 1
                    except:
                        continue
                
                embed = discord.Embed(
                    title="✅ Playlist Added",
                    description=f"**{playlist_info['name']}**\nAdded {added_count} tracks to queue!",
                    color=0x00ff00
                )
                await loading_msg.edit(embed=embed)
                
                # Start playing if nothing is playing
                if not voice_clients[guild_id].is_playing():
                    await play_next(ctx)
                return
        
        # Handle Spotify tracks
        elif 'spotify.com/track' in query:
            spotify_info = await get_spotify_track_info(query)
            if spotify_info:
                query = spotify_info['search_query']
                embed = discord.Embed(
                    title="🎵 Processing Spotify Track",
                    description=f"Searching for: **{spotify_info['title']}** by **{spotify_info['artist']}**",
                    color=0x1DB954
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Could not process Spotify link. Please try a YouTube link or search query.")
                return
        
        # Add "ytsearch:" prefix if it's not a URL
        if not is_url(query):
            query = f"ytsearch:{query}"
        
        # Create loading message
        loading_embed = discord.Embed(
            title="🔍 Searching...",
            description=f"Looking for: **{query.replace('ytsearch:', '')}**",
            color=0xffff00
        )
        loading_msg = await ctx.send(embed=loading_embed)
        
        try:
            # Get music source
            source = await MusicSource.from_url(query, loop=bot.loop, stream=True)
            
            # Add to queue
            music_queues[guild_id].add({
                'source': source,
                'title': source.title,
                'url': source.url,
                'duration': source.duration,
                'thumbnail': source.thumbnail,
                'uploader': source.uploader,
                'requester': ctx.author
            })
            
            # If nothing is playing, start playing
            if not voice_clients[guild_id].is_playing():
                await play_next(ctx)
            else:
                # Song added to queue
                embed = discord.Embed(
                    title="➕ Added to Queue",
                    description=f"**{source.title}**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="Duration", 
                    value=format_music_duration(source.duration), 
                    inline=True
                )
                embed.add_field(
                    name="Position in Queue", 
                    value=f"{len(music_queues[guild_id].queue)}", 
                    inline=True
                )
                embed.add_field(
                    name="Requested by", 
                    value=ctx.author.mention, 
                    inline=True
                )
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
                embed.set_footer(text="🎵 Advanced Music Bot | Running on Cloud ☁️")
                
                await loading_msg.edit(embed=embed)
                
        except Exception as e:
            logger.error(f"Error playing music: {e}")
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Could not play the requested song: {str(e)}",
                color=0xff0000
            )
            await loading_msg.edit(embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in play command: {e}")
        await ctx.send(f"❌ An error occurred: {str(e)}")

async def play_next(ctx):
    """Play the next song in queue"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues or guild_id not in voice_clients:
            return
        
        queue = music_queues[guild_id]
        voice_client = voice_clients[guild_id]
        
        next_song = queue.next()
        if next_song:
            # Create now playing embed
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{next_song['title']}**",
                color=0x00ff00
            )
            embed.add_field(
                name="Duration", 
                value=format_music_duration(next_song['duration']), 
                inline=True
            )
            embed.add_field(
                name="Requested by", 
                value=next_song['requester'].mention, 
                inline=True
            )
            
            # Add queue info
            queue_info = f"Loop: {queue.loop_mode.title()}"
            if queue.shuffle:
                queue_info += " | Shuffle: On"
            embed.add_field(
                name="Queue Info", 
                value=queue_info, 
                inline=True
            )
            
            if next_song.get('uploader'):
                embed.add_field(
                    name="Channel", 
                    value=next_song['uploader'], 
                    inline=True
                )
            if next_song.get('thumbnail'):
                embed.set_thumbnail(url=next_song['thumbnail'])
            embed.set_footer(text="🎵 Advanced Music Bot | Running on Cloud ☁️")
            
            await ctx.send(embed=embed)
            
            # Play the song
            voice_client.play(
                next_song['source'], 
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(ctx), bot.loop
                ) if not e else logger.error(f"Player error: {e}")
            )
        else:
            # Queue is empty
            embed = discord.Embed(
                title="🔇 Queue Empty",
                description="No more songs in queue. Add more songs with `!play <song>`",
                color=0x808080
            )
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error playing next song: {e}")

@bot.command(name='skip', aliases=['s'])
async def skip_song(ctx):
    """Skip the current song"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in voice_clients or not voice_clients[guild_id].is_playing():
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        voice_clients[guild_id].stop()
        
        embed = discord.Embed(
            title="⏭️ Song Skipped",
            description="Playing next song in queue...",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error skipping song: {e}")
        await ctx.send(f"❌ Error skipping song: {str(e)}")

@bot.command(name='loop')
async def loop_command(ctx, mode=None):
    """Set loop mode: off, song, queue"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        queue = music_queues[guild_id]
        
        if mode is None:
            # Show current loop mode
            embed = discord.Embed(
                title="🔄 Loop Mode",
                description=f"Current mode: **{queue.loop_mode.title()}**\n\nAvailable modes:\n`off` - No looping\n`song` - Loop current song\n`queue` - Loop entire queue",
                color=0x0099ff
            )
            await ctx.send(embed=embed)
            return
        
        if queue.set_loop_mode(mode.lower()):
            loop_emojis = {"off": "⏹️", "song": "🔂", "queue": "🔁"}
            embed = discord.Embed(
                title=f"{loop_emojis.get(mode.lower(), '🔄')} Loop Mode Changed",
                description=f"Loop mode set to: **{mode.title()}**",
                color=0x00ff00
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Invalid loop mode! Use: `off`, `song`, or `queue`")
        
    except Exception as e:
        logger.error(f"Error setting loop mode: {e}")
        await ctx.send(f"❌ Error setting loop mode: {str(e)}")

@bot.command(name='shuffle')
async def shuffle_command(ctx):
    """Toggle shuffle mode"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        queue = music_queues[guild_id]
        shuffle_status = queue.toggle_shuffle()
        
        embed = discord.Embed(
            title="🔀 Shuffle Mode",
            description=f"Shuffle is now: **{'On' if shuffle_status else 'Off'}**",
            color=0x00ff00 if shuffle_status else 0xff0000
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error toggling shuffle: {e}")
        await ctx.send(f"❌ Error toggling shuffle: {str(e)}")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx, page=1):
    """Show the current music queue"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        queue = music_queues[guild_id]
        
        if not queue.queue and not queue.current:
            embed = discord.Embed(
                title="📝 Music Queue",
                description="Queue is empty. Add songs with `!play <song>`",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="📝 Music Queue",
            color=0x0099ff
        )
        
        # Show currently playing
        if queue.current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"**{queue.current['title']}**\nRequested by: {queue.current['requester'].mention}",
                inline=False
            )
        
        # Show queue settings
        settings = f"Loop: {queue.loop_mode.title()}"
        if queue.shuffle:
            settings += " | Shuffle: On"
        embed.add_field(
            name="⚙️ Settings",
            value=settings,
            inline=False
        )
        
        # Show queue with pagination
        if queue.queue:
            songs_per_page = 10
            total_pages = (len(queue.queue) - 1) // songs_per_page + 1
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * songs_per_page
            end_idx = start_idx + songs_per_page
            
            queue_text = ""
            for i, song in enumerate(list(queue.queue)[start_idx:end_idx], start_idx + 1):
                queue_text += f"{i}. **{song['title']}** - {song['requester'].mention}\n"
            
            embed.add_field(
                name=f"⏭️ Up Next (Page {page}/{total_pages})",
                value=queue_text,
                inline=False
            )
            
            if total_pages > 1:
                embed.set_footer(text=f"Use !queue {page+1} for next page | 🎵 Advanced Music Bot")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error showing queue: {e}")
        await ctx.send(f"❌ Error showing queue: {str(e)}")

@bot.command(name='remove', aliases=['rm'])
async def remove_song(ctx, index: int):
    """Remove a song from the queue by index"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        queue = music_queues[guild_id]
        removed_song = queue.remove(index - 1)  # Convert to 0-based index
        
        if removed_song:
            embed = discord.Embed(
                title="🗑️ Song Removed",
                description=f"Removed: **{removed_song['title']}**",
                color=0xff0000
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Invalid queue position!")
        
    except ValueError:
        await ctx.send("❌ Please provide a valid number!")
    except Exception as e:
        logger.error(f"Error removing song: {e}")
        await ctx.send(f"❌ Error removing song: {str(e)}")

@bot.command(name='clear')
async def clear_queue(ctx):
    """Clear the entire music queue"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        music_queues[guild_id].clear()
        
        embed = discord.Embed(
            title="🗑️ Queue Cleared",
            description="All songs have been removed from the queue.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error clearing queue: {e}")
        await ctx.send(f"❌ Error clearing queue: {str(e)}")

@bot.command(name='history')
async def show_history(ctx):
    """Show recently played songs"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues:
            await ctx.send("❌ No music queue found!")
            return
        
        queue = music_queues[guild_id]
        
        if not queue.history:
            embed = discord.Embed(
                title="📜 Play History",
                description="No songs in history yet.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="📜 Recently Played",
            color=0x0099ff
        )
        
        history_text = ""
        for i, song in enumerate(reversed(list(queue.history)[-10:]), 1):  # Last 10 songs
            history_text += f"{i}. **{song['title']}** - {song['requester'].mention}\n"
        
        embed.add_field(
            name="🎵 Last 10 Songs",
            value=history_text,
            inline=False
        )
        
        embed.set_footer(text="🎵 Advanced Music Bot | Running on Cloud ☁️")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error showing history: {e}")
        await ctx.send(f"❌ Error showing history: {str(e)}")

@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    """Show currently playing song with detailed info"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id not in music_queues or guild_id not in voice_clients:
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        if not voice_clients[guild_id].is_playing():
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        queue = music_queues[guild_id]
        current = queue.current
        
        if not current:
            await ctx.send("❌ No current song information available!")
            return
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{current['title']}**",
            color=0x00ff00
        )
        
        embed.add_field(
            name="Duration", 
            value=format_music_duration(current['duration']), 
            inline=True
        )
        embed.add_field(
            name="Requested by", 
            value=current['requester'].mention, 
            inline=True
        )
        embed.add_field(
            name="Volume", 
            value=f"{int(queue.volume * 100)}%", 
            inline=True
        )
        
        if current.get('uploader'):
            embed.add_field(
                name="Channel", 
                value=current['uploader'], 
                inline=True
            )
        
        # Queue info
        queue_info = f"Loop: {queue.loop_mode.title()}"
        if queue.shuffle:
            queue_info += " | Shuffle: On"
        embed.add_field(
            name="Queue Settings", 
            value=queue_info, 
            inline=True
        )
        
        embed.add_field(
            name="Songs in Queue", 
            value=str(len(queue.queue)), 
            inline=True
        )
        
        if current.get('thumbnail'):
            embed.set_thumbnail(url=current['thumbnail'])
        
        embed.set_footer(text="🎵 Advanced Music Bot | Running on Cloud ☁️")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error showing now playing: {e}")
        await ctx.send(f"❌ Error showing now playing: {str(e)}")

# Keep existing commands (stop, leave, volume, attendance, etc.)
@bot.command(name='stop')
async def stop_music(ctx):
    """Stop music and clear queue"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id in music_queues:
            music_queues[guild_id].clear()
        
        if guild_id in voice_clients:
            voice_clients[guild_id].stop()
        
        embed = discord.Embed(
            title="⏹️ Music Stopped",
            description="Queue cleared and playback stopped.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error stopping music: {e}")
        await ctx.send(f"❌ Error stopping music: {str(e)}")

@bot.command(name='leave', aliases=['disconnect'])
async def leave_voice(ctx):
    """Make the bot leave the voice channel"""
    try:
        guild_id = ctx.guild.id
        
        if guild_id in voice_clients:
            await voice_clients[guild_id].disconnect()
            del voice_clients[guild_id]
            
            if guild_id in music_queues:
                music_queues[guild_id].clear()
            
            embed = discord.Embed(
                title="👋 Disconnected",
                description="Left the voice channel and cleared the queue.",
                color=0x808080
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ I'm not connected to a voice channel!")
            
    except Exception as e:
        logger.error(f"Error leaving voice channel: {e}")
        await ctx.send(f"❌ Error leaving voice channel: {str(e)}")

@bot.command(name='volume', aliases=['vol'])
async def set_volume(ctx, volume: int):
    """Set the music volume (0-100)"""
    try:
        if volume < 0 or volume > 100:
            await ctx.send("❌ Volume must be between 0 and 100!")
            return
        
        guild_id = ctx.guild.id
        
        if guild_id not in voice_clients or not voice_clients[guild_id].is_playing():
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        # Set volume
        voice_clients[guild_id].source.volume = volume / 100
        music_queues[guild_id].volume = volume / 100
        
        embed = discord.Embed(
            title="🔊 Volume Changed",
            description=f"Volume set to **{volume}%**",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error setting volume: {e}")
        await ctx.send(f"❌ Error setting volume: {str(e)}")

# Keep all existing attendance commands and functions
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
                    
                    embed.set_footer(text=f"🎵 Advanced Music & Attendance Bot | Running on Cloud ☁️")
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
            
            embed.set_footer(text=f"🎵 Advanced Music & Attendance Bot | Running on Cloud ☁️")
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in attendance command: {e}")
        await ctx.send("❌ An error occurred while fetching attendance data.")

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

@bot.command(name='ping')
async def ping(ctx):
    """Check if bot is responsive"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"🎵 Advanced Music & Attendance Bot running on cloud ☁️\nLatency: {latency}ms",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="🎵 Advanced Music & Attendance Bot Commands",
        description="Your all-in-one Discord bot with advanced music features and attendance tracking!",
        color=0x0099ff
    )
    
    # Music commands
    embed.add_field(
        name="🎵 Music Commands",
        value="`!play <song/url>` - Play music from YouTube or Spotify\n"
              "`!skip` - Skip current song\n"
              "`!stop` - Stop music and clear queue\n"
              "`!queue [page]` - Show music queue\n"
              "`!volume <0-100>` - Set volume\n"
              "`!leave` - Disconnect from voice channel",
        inline=False
    )
    
    # Advanced music commands
    embed.add_field(
        name="🎛️ Advanced Music",
        value="`!loop <off/song/queue>` - Set loop mode\n"
              "`!shuffle` - Toggle shuffle mode\n"
              "`!remove <#>` - Remove song from queue\n"
              "`!clear` - Clear entire queue\n"
              "`!history` - Show recently played songs\n"
              "`!nowplaying` - Show current song details",
        inline=False
    )
    
    # Attendance commands
    embed.add_field(
        name="📊 Attendance Commands",
        value="`!attendance` - Show server attendance summary\n"
              "`!attendance @user` - Show user attendance details\n"
              "`!ping` - Check bot status",
        inline=False
    )
    
    embed.set_footer(text="🎵 Advanced Music & Attendance Bot | Running on Cloud ☁️")
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
        logger.info("Starting Advanced Discord Music & Attendance Bot...")
        logger.info("Bot will run 24/7 on cloud infrastructure")
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            exit(1)
