"""Telegram bot for Alisa AI Assistant."""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from alisa.core.config import get_config
from alisa.core.assistant import AlisaAssistant
from alisa.reception.greeter import ReceptionGreeter
from alisa.voice.stt import transcribe
from alisa.services.profiler import get_profiler

logger = logging.getLogger(__name__)

class AlisaBot:
    """Telegram bot interface for Alisa."""
    
    def __init__(self, assistant=None, greeter=None):
        self.config = get_config()
        # Check environment first, then config
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN') or self.config.get('telegram', {}).get('bot_token')
        if not self.bot_token:
            raise ValueError("Telegram bot_token not found in environment or config")
        
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID') or self.config.get('telegram', {}).get('chat_id')
        # Use provided instances or create new ones (fallback for standalone mode)
        self.assistant = assistant or AlisaAssistant()
        self.greeter = greeter or ReceptionGreeter(telegram_notifier=self._send_notification)
        self.reception_task = None
        self.app = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "Salom! Men Alisa AI assistantman. Savollaringizni yuboring yoki quyidagi buyruqlardan foydalaning:\n"
            "/status - tizim holati\n"
            "/memory - xotira bosimi tekshirish\n"
            "/performance - performance statistikasi\n"
            "/ask <savol> - savol berish\n"
            "/clear_memory - suhbat xotirasini tozalash\n"
            "/mode - joriy rejimlar\n"
            "/update - tizimni yangilash\n"
            "/restart - tizimni qayta ishga tushirish\n"
            "/reception_start - resepsiya rejimini boshlash\n"
            "/reception_stop - resepsiya rejimini to'xtatish\n"
            "/guests - mehmonlar ro'yxati\n"
            "/orchestrate - AI orchestrator ishga tushirish\n"
            "/help - yordam\n\n"
            "🎤 Ovozli xabar ham yuborishingiz mumkin!"
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            from alisa.services.health import format_system_status
            from alisa.services.updater import get_current_version
            from alisa.core.memory_manager import get_memory_manager
            from alisa.brain.llm_manager import get_llm_manager
            
            status_text = "🤖 Alisa Status:\n\n"
            status_text += format_system_status()
            
            # Add LLM provider info
            try:
                manager = get_llm_manager()
                provider_status = manager.get_provider_status()
                if provider_status.get('last_successful'):
                    status_text += f"\n🧠 Joriy LLM provider: {provider_status['last_successful']}\n"
                status_text += f"   Faol providerlar: {provider_status['active_providers']}\n"
            except Exception as e:
                logger.warning(f"Could not get LLM provider status: {e}")
            
            # Add memory management info
            memory_manager = get_memory_manager()
            memory_stats = memory_manager.get_memory_stats()
            if memory_stats:
                status_text += f"\n🧠 Memory Management:\n"
                status_text += f"   RSS: {memory_stats['rss_mb']:.1f} MB\n"
                status_text += f"   VMS: {memory_stats['vms_mb']:.1f} MB\n"
                status_text += f"   Usage: {memory_stats['percent']:.1f}%\n"
                if memory_stats['percent'] > 80:
                    status_text += "   ⚠️ High memory usage detected"
            
            # Add version info
            version = get_current_version()
            if version:
                status_text += f"\n📦 Version: {version}"
            
            await update.message.reply_text(status_text)
        except Exception as e:
            logger.error(f"Status command error: {e}")
            await update.message.reply_text("Status ma'lumotini olishda xatolik yuz berdi.")

    async def providers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /providers command - show LLM provider status."""
        try:
            from alisa.brain.llm_manager import get_llm_manager
            
            manager = get_llm_manager()
            status = manager.get_provider_status()
            
            message = "🤖 LLM Providerlar holati:\n\n"
            message += f"📊 Faol providerlar: {status['active_providers']}\n"
            
            if status['last_successful']:
                message += f"✅ Oxirgi muvaffaqiyatli: {status['last_successful']}\n"
            
            message += "\n📋 Provider tafsilotlari:\n"
            
            for name, info in status['providers'].items():
                emoji = "✅" if info['available'] else "❌"
                message += f"\n{emoji} {name.upper()}:\n"
                message += f"   📈 So'rovlar: {info['requests']}\n"
                message += f"   🎯 Muvaffaqiyat: {info['success_rate']}\n"
                message += f"   ⏱️ O'rtacha vaqt: {info['avg_response_time']}\n"
                
                if info['last_error']:
                    # Truncate error to 60 chars as required by the plan
                    error_msg = info['last_error']
                    if len(error_msg) > 60:
                        error_msg = error_msg[:57] + "..."
                    message += f"   ❌ Oxirgi xato: {error_msg}\n"
            
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Providers command error: {e}")
            await update.message.reply_text("❌ Provider holatini olishda xatolik yuz berdi.")

    async def memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /memory command - check memory pressure."""
        try:
            from alisa.services.health import check_memory_pressure
            pressure_info = check_memory_pressure()
            
            level_emoji = {
                "normal": "✅",
                "moderate": "⚠️", 
                "high": "🔶",
                "critical": "🔴",
                "unknown": "❓"
            }
            
            emoji = level_emoji.get(pressure_info["pressure_level"], "❓")
            
            message = f"{emoji} Xotira bosimi: {pressure_info['pressure_level']}\n"
            message += f"💾 Mavjud xotira: {pressure_info['available_mb']} MB\n"
            message += f"📊 RAM ishlatilgan: {pressure_info['memory_percent']}%\n"
            message += f"🔄 Swap ishlatilgan: {pressure_info['swap_percent']}%\n\n"
            
            if pressure_info["suggestions"]:
                message += "💡 Tavsiyalar:\n"
                for suggestion in pressure_info["suggestions"]:
                    message += f"• {suggestion}\n"
            
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Memory command error: {e}")
            await update.message.reply_text("❌ Xotira holatini tekshirishda xatolik yuz berdi.")
    
    async def performance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command - show performance statistics."""
        try:
            profiler = get_profiler()
            stats = profiler.get_stats()
            
            if not stats:
                await update.message.reply_text("📊 Hozircha performance ma'lumotlari yo'q.")
                return
            
            message = "📊 Performance Statistics:\n\n"
            
            # Sort operations by average duration (slowest first)
            sorted_ops = sorted(stats.items(), key=lambda x: x[1]['avg_ms'], reverse=True)
            
            for operation, data in sorted_ops[:10]:  # Show top 10 slowest operations
                avg_ms = data['avg_ms']
                count = data['count']
                min_ms = data['min_ms']
                max_ms = data['max_ms']
                
                # Add emoji based on performance
                if avg_ms > 3000:  # > 3 seconds
                    emoji = "🔴"
                elif avg_ms > 1000:  # > 1 second
                    emoji = "🟡"
                else:
                    emoji = "🟢"
                
                message += f"{emoji} {operation}:\n"
                message += f"   Avg: {avg_ms:.1f}ms\n"
                message += f"   Range: {min_ms:.1f}-{max_ms:.1f}ms\n"
                message += f"   Count: {count}\n\n"
            
            # Show slow operations (> 3 seconds)
            slow_ops = profiler.get_slow_operations(threshold_ms=3000)
            if slow_ops:
                message += f"⚠️ Slow operations (>{3000}ms):\n"
                for op in slow_ops[-5:]:  # Show last 5 slow operations
                    message += f"• {op.operation}: {op.duration_ms:.1f}ms\n"
            
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Performance command error: {e}")
            await update.message.reply_text("❌ Performance ma'lumotlarini olishda xatolik yuz berdi.")
    
    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ask command."""
        if not context.args:
            await update.message.reply_text("Iltimos, savol yuboring: /ask <savolingiz>")
            return
        
        question = " ".join(context.args)
        await self._process_question(update, question)
    
    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /update command."""
        try:
            from alisa.services.updater import check_git_status, perform_update
            
            await update.message.reply_text("🔍 Yangilanishlar tekshirilmoqda...")
            
            # Check for updates
            has_updates, message = check_git_status()
            
            if not has_updates:
                await update.message.reply_text(f"✅ {message}")
                return
            
            await update.message.reply_text(f"📥 {message}\n\nYangilanish boshlanmoqda...")
            
            # Perform update
            success, update_message = perform_update()
            
            if success:
                await update.message.reply_text(f"✅ {update_message}\n\n🔄 Tizim qayta ishga tushirilmoqda...")
            else:
                await update.message.reply_text(f"❌ Yangilanish xatoligi: {update_message}")
                
        except Exception as e:
            logger.error(f"Update command error: {e}")
            await update.message.reply_text("Yangilanishda xatolik yuz berdi.")
    
    async def restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /restart command."""
        try:
            from alisa.services.updater import restart_service
            
            await update.message.reply_text("🔄 Tizim qayta ishga tushirilmoqda...")
            
            # Restart service
            success, message = restart_service()
            
            if success:
                await update.message.reply_text(f"✅ {message}")
            else:
                await update.message.reply_text(f"❌ Qayta ishga tushirishda xatolik: {message}")
                
        except Exception as e:
            logger.error(f"Restart command error: {e}")
            await update.message.reply_text("Qayta ishga tushirishda xatolik yuz berdi.")
    
    async def mode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mode command to show/set operational mode."""
        try:
            # If no arguments, show current mode
            if not context.args:
                mode_info = "🔧 Alisa rejimi:\n\n"
                
                # Check which modes are active
                current_mode = self._get_current_mode()
                mode_info += f"📍 Joriy rejim: {current_mode}\n\n"
                
                if hasattr(self, 'assistant') and self.assistant:
                    mode_info += "🎤 Ovozli rejim: Faol\n"
                else:
                    mode_info += "🎤 Ovozli rejim: Faol emas\n"
                
                mode_info += "💬 Telegram rejim: Faol\n"  # Always active if bot is running
                
                if self.greeter.is_active:
                    mode_info += "🏢 Resepsiya rejim: Faol\n"
                else:
                    mode_info += "🏢 Resepsiya rejim: Faol emas\n"
                
                # Add system info
                from alisa.brain.online import is_online
                if is_online():
                    mode_info += "🌐 Internet: Mavjud\n"
                else:
                    mode_info += "🌐 Internet: Mavjud emas (offline rejim)\n"
                
                mode_info += "\n💡 Rejimni o'zgartirish: /mode reception yoki /mode assistant"
                
                await update.message.reply_text(mode_info)
                return
            
            # Set mode based on argument
            new_mode = context.args[0].lower()
            
            if new_mode == "reception":
                self._set_mode("reception")
                await update.message.reply_text("🏢 Resepsiya rejimiga o'tkazildi. Mehmonlarni kutib olishga tayyorman!")
            elif new_mode == "assistant":
                self._set_mode("assistant")
                await update.message.reply_text("🤖 Assistant rejimiga o'tkazildi. Savollaringizni kutmoqdaman!")
            else:
                await update.message.reply_text(
                    "❌ Noto'g'ri rejim. Faqat 'reception' yoki 'assistant' rejimlarini tanlashingiz mumkin.\n"
                    "Misol: /mode reception"
                )
            
        except Exception as e:
            logger.error(f"Mode command error: {e}")
            await update.message.reply_text("Rejim ma'lumotini olishda xatolik yuz berdi.")
    
    def _get_current_mode(self) -> str:
        """Get current operational mode."""
        try:
            import json
            state_file = "/tmp/alisa_mode_state.json"
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    return state.get('mode', 'assistant')
            return 'assistant'  # Default mode
        except Exception:
            return 'assistant'
    
    def _set_mode(self, mode: str):
        """Set operational mode and persist to state file."""
        try:
            import json
            state_file = "/tmp/alisa_mode_state.json"
            state = {'mode': mode, 'timestamp': time.time()}
            with open(state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Failed to set mode: {e}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages."""
        if update.message.text:
            await self._process_question(update, update.message.text)
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice/audio messages."""
        try:
            # Send processing indicator
            await update.message.chat.send_action("typing")
            await update.message.reply_text("🎤 Ovozli xabaringizni qayta ishlamoqdaman...")
            
            # Get voice file
            voice_file = None
            if update.message.voice:
                voice_file = update.message.voice
            elif update.message.audio:
                voice_file = update.message.audio
            else:
                await update.message.reply_text("Ovozli xabar topilmadi.")
                return
            
            # Download voice file
            file = await voice_file.get_file()
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_ogg:
                await file.download_to_drive(temp_ogg.name)
                temp_ogg_path = temp_ogg.name
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
            
            try:
                # Convert OGG/MP3 to 16k mono WAV using ffmpeg
                subprocess.run([
                    'ffmpeg', '-i', temp_ogg_path, 
                    '-ar', '16000', '-ac', '1', '-y', 
                    temp_wav_path
                ], check=True, capture_output=True)
                
                # Read FULL WAV file as bytes (don't skip header)
                with open(temp_wav_path, 'rb') as f:
                    audio_data = f.read()
                
                # Transcribe audio
                transcript = transcribe(audio_data)
                
                if not transcript:
                    await update.message.reply_text("Ovozli xabaringizni tushuna olmadim.")
                    return
                
                # Process transcript through assistant
                response = await self.assistant.process_text(transcript)
                
                # Send response
                response_text = f"📝 Siz aytdingiz: \"{transcript}\"\n\n🤖 Javob: {response or 'Kechirasiz, javob bera olmadim.'}"
                await update.message.reply_text(response_text)
                
            finally:
                # Clean up temporary files
                try:
                    os.unlink(temp_ogg_path)
                except:
                    pass
                try:
                    os.unlink(temp_wav_path)
                except:
                    pass
                    
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion error: {e}")
            await update.message.reply_text("Ovozli xabarni qayta ishlashda xatolik yuz berdi.")
        except Exception as e:
            logger.error(f"Voice message processing error: {e}")
            await update.message.reply_text("Ovozli xabarni qayta ishlashda xatolik yuz berdi.")
    
    async def clear_memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear_memory command."""
        try:
            self.assistant.memory.clear()
            await update.message.reply_text("🧠 Suhbat xotirasi tozalandi.")
        except Exception as e:
            logger.error(f"Clear memory error: {e}")
            await update.message.reply_text("Xotirani tozalashda xatolik yuz berdi.")
    
    async def _process_question(self, update: Update, question: str):
        """Process a question and send response."""
        try:
            # Send typing indicator
            await update.message.chat.send_action("typing")
            
            # Get response from assistant
            response = await self.assistant.process_text(question)
            
            # Send response
            await update.message.reply_text(response or "Kechirasiz, javob bera olmadim.")
            
        except Exception as e:
            logger.error(f"Question processing error: {e}")
            await update.message.reply_text("Xatolik yuz berdi. Keyinroq urinib ko'ring.")
    
    async def reception_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reception_start command."""
        try:
            if self.greeter.is_active:
                await update.message.reply_text("Resepsiya rejimi allaqachon faol.")
                return
            
            # Start reception mode in background
            self.reception_task = asyncio.create_task(self.greeter.start_reception_mode())
            await update.message.reply_text("🏢 Resepsiya rejimi boshlandi. Mehmonlarni kutib olishga tayyorman!")
            
        except Exception as e:
            logger.error(f"Reception start error: {e}")
            await update.message.reply_text("Resepsiya rejimini boshlashda xatolik yuz berdi.")
    
    async def reception_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reception_stop command."""
        try:
            if not self.greeter.is_active:
                await update.message.reply_text("Resepsiya rejimi faol emas.")
                return
            
            self.greeter.stop_reception_mode()
            
            # Cancel the reception task if it exists
            if self.reception_task and not self.reception_task.done():
                self.reception_task.cancel()
                try:
                    await self.reception_task
                except asyncio.CancelledError:
                    pass
                self.reception_task = None
            
            await update.message.reply_text("🛑 Resepsiya rejimi to'xtatildi.")
            
        except Exception as e:
            logger.error(f"Reception stop error: {e}")
            await update.message.reply_text("Resepsiya rejimini to'xtatishda xatolik yuz berdi.")
    
    async def guests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /guests command."""
        try:
            guest_log = self.greeter.get_guest_log()
            
            if not guest_log:
                await update.message.reply_text("Bugun mehmonlar kelmagan.")
                return
            
            guest_text = "👥 Bugungi mehmonlar:\n\n"
            for i, guest in enumerate(guest_log[-10:], 1):  # Show last 10
                guest_text += f"{i}. {guest['time']}\n"
            
            await update.message.reply_text(guest_text)
            
        except Exception as e:
            logger.error(f"Guests command error: {e}")
            await update.message.reply_text("Mehmonlar ro'yxatini olishda xatolik yuz berdi.")
    
    async def _send_notification(self, message: str):
        """Send notification to configured chat."""
        if not self.app or not self.chat_id:
            return
        
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as e:
            logger.error(f"Notification send error: {e}")
    
    async def send_notification(self, message: str):
        """Public method to send notifications."""
        await self._send_notification(message)

    async def orchestrate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orchestrate command - run AI orchestrator."""
        # Check authorization - only allow configured chat_id
        if self.chat_id and str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ Sizga bu buyruqni ishlatish ruxsati yo'q.")
            return
        
        try:
            # ACK-reply immediately
            await update.message.reply_text("🤖 AI Orchestrator ishga tushirilmoqda... (dry-run rejimida)")
            
            # Launch orchestrator in background thread (non-blocking)
            self._orchestrator_task = asyncio.create_task(self._run_orchestrator_async())
            
        except Exception as e:
            logger.error(f"Orchestrate command error: {e}")
            await update.message.reply_text("Orchestrator ishga tushirishda xatolik yuz berdi.")
    
    async def _run_orchestrator_async(self):
        """Run AI orchestrator in background and send results."""
        try:
            # Run orchestrator in thread to avoid blocking
            result = await asyncio.to_thread(self._run_orchestrator_sync)
            
            # Send result notification
            if result:
                await self._send_notification(f"🤖 AI Orchestrator natijasi:\n\n```json\n{result}\n```")
            else:
                await self._send_notification("❌ AI Orchestrator xatolik bilan tugadi.")
                
        except Exception as e:
            logger.error(f"Orchestrator async execution error: {e}")
            await self._send_notification(f"❌ AI Orchestrator xatoligi: {str(e)}")
    
    def _run_orchestrator_sync(self) -> Optional[str]:
        """Run AI orchestrator synchronously and return JSON result."""
        try:
            # Set dry-run environment variable
            env = os.environ.copy()
            env['ALISA_ORCHESTRATOR_DRY_RUN'] = '1'
            
            # Run ai_orchestrator command
            result = subprocess.run([
                'python', '-m', 'ai_orchestrator'
            ], 
            capture_output=True, 
            text=True, 
            timeout=300,  # 5 minute timeout
            env=env,
            cwd=os.getcwd()
            )
            
            if result.returncode == 0:
                # Try to extract JSON from output
                output_lines = result.stdout.strip().split('\n')
                for line in reversed(output_lines):  # Check from end for JSON
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            # Validate it's proper JSON
                            json.loads(line)
                            return line
                        except json.JSONDecodeError:
                            continue
                
                # If no JSON found, return summary
                return json.dumps({
                    "status": "completed",
                    "message": "Orchestrator muvaffaqiyatli tugadi",
                    "output_preview": result.stdout[-500:] if result.stdout else "No output"
                })
            else:
                return json.dumps({
                    "status": "error", 
                    "message": f"Orchestrator xatolik bilan tugadi (exit code: {result.returncode})",
                    "error": result.stderr[-500:] if result.stderr else "No error details"
                })
                
        except subprocess.TimeoutExpired:
            return json.dumps({
                "status": "timeout",
                "message": "Orchestrator 5 daqiqada tugamadi (timeout)"
            })
        except Exception as e:
            logger.error(f"Orchestrator sync execution error: {e}")
            return json.dumps({
                "status": "exception",
                "message": f"Orchestrator ichki xatoligi: {str(e)}"
            })

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "🤖 Alisa AI Assistant\n\n"
            "Buyruqlar:\n"
            "/start - botni ishga tushirish\n"
            "/status - tizim holati\n"
            "/providers - LLM providerlar holati\n"
            "/memory - xotira bosimi tekshirish\n"
            "/ask <savol> - savol berish\n"
            "/mode - joriy rejimlar\n"
            "/update - tizimni yangilash\n"
            "/restart - tizimni qayta ishga tushirish\n"
            "/reception_start - resepsiya rejimini boshlash\n"
            "/reception_stop - resepsiya rejimini to'xtatish\n"
            "/guests - mehmonlar ro'yxati\n"
            "/orchestrate - AI orchestrator ishga tushirish\n"
            "/help - bu yordam\n\n"
            "Shuningdek, oddiy xabar yuborib ham savol berishingiz mumkin."
        )
        await update.message.reply_text(help_text)
    
    async def start_bot(self):
        """Start the Telegram bot."""
        try:
            # Create application
            self.app = Application.builder().token(self.bot_token).build()
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("status", self.status_command))
            self.app.add_handler(CommandHandler("providers", self.providers_command))
            self.app.add_handler(CommandHandler("memory", self.memory_command))
            self.app.add_handler(CommandHandler("performance", self.performance_command))
            self.app.add_handler(CommandHandler("ask", self.ask_command))
            self.app.add_handler(CommandHandler("mode", self.mode_command))
            self.app.add_handler(CommandHandler("update", self.update_command))
            self.app.add_handler(CommandHandler("restart", self.restart_command))
            self.app.add_handler(CommandHandler("clear_memory", self.clear_memory_command))
            self.app.add_handler(CommandHandler("reception_start", self.reception_start_command))
            self.app.add_handler(CommandHandler("reception_stop", self.reception_stop_command))
            self.app.add_handler(CommandHandler("guests", self.guests_command))
            self.app.add_handler(CommandHandler("orchestrate", self.orchestrate_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice_message))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            # Start bot
            logger.info("Starting Telegram bot...")
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
            
            logger.info("Telegram bot started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
    
    async def stop_bot(self):
        """Stop the Telegram bot."""
        # Stop reception mode if active
        if self.greeter.is_active:
            self.greeter.stop_reception_mode()
        
        # Cancel reception task if running
        if self.reception_task and not self.reception_task.done():
            self.reception_task.cancel()
            try:
                await self.reception_task
            except asyncio.CancelledError:
                pass
        
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        
        logger.info("Telegram bot stopped")

async def main():
    """Run the Telegram bot."""
    logging.basicConfig(level=logging.INFO)
    
    bot = AlisaBot()
    try:
        await bot.start_bot()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bot.stop_bot()

if __name__ == "__main__":
    asyncio.run(main())
