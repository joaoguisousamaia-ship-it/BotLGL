import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_PATH = Path("config.json")
TICKET_CATEGORY_NAME = "Tickets"
QUESTION_TIMEOUT = 300
CHANNEL_DELETION_DELAY_SECONDS = 3

DEFAULT_QUESTIONS = [
    "Qual e o seu nome ingame?",
    "Qual e a sua idade em Narnia?",
    "Qual e a sua profissao ingame?",
    "O que voce espera aqui no Legal?",
    "Tem algum feedback ou comentario adicional?",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("botlgl")


def normalize_channel_slug(raw_name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw_name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug[:70] if slug else "usuario"
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"guilds": {}}

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if "guilds" not in data or not isinstance(data["guilds"], dict):
        data["guilds"] = {}
    return data


def save_config(config_data: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config_data, file, ensure_ascii=False, indent=2)


config = load_config()
sessions: dict[int, dict] = {}


def get_guild_config(guild_id: int) -> dict:
    guilds = config.setdefault("guilds", {})
    return guilds.setdefault(
        str(guild_id),
        {
            "reviewer_role_id": None,
            "logs_channel_id": None,
            "cargo_logs_channel_id": None,
            "transcripts_channel_id": None,
            "ticket_panel_channel_id": None,
            "ticket_category_id": None,
            "staff_role_id": None,
        },
    )


def update_guild_config(guild_id: int, key: str, value: int | None) -> None:
    guild_config = get_guild_config(guild_id)
    guild_config[key] = value
    save_config(config)


def get_guild_questions(guild_id: int) -> list[str]:
    guild_config = get_guild_config(guild_id)
    custom = guild_config.get("custom_questions")
    if custom and isinstance(custom, list) and len(custom) > 0:
        return custom
    return DEFAULT_QUESTIONS


def get_channel_from_config(guild: discord.Guild, channel_id: int | None) -> discord.abc.GuildChannel | None:
    if not channel_id:
        return None
    return guild.get_channel(channel_id)


def get_role_from_config(guild: discord.Guild, role_id: int | None) -> discord.Role | None:
    if not role_id:
        return None
    return guild.get_role(role_id)


def build_transcript_embed(session: dict, channel_mention: str) -> discord.Embed:
    lines = []
    for index, item in enumerate(session["respostas"], start=1):
        lines.append(f"**P{index}:** {item['pergunta']}")
        lines.append(f"**R{index}:** {item['resposta']}")
        lines.append("")

    description = "\n".join(lines).strip() or "Sem respostas registradas."
    embed = discord.Embed(
        title="Novo transcript para revisao",
        description=description,
        color=discord.Color.gold(),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="Informacoes",
        value=(
            f"**Usuario:** {session['user']}\n"
            f"**Canal:** {channel_mention}\n"
            f"**Hora:** {session['time']}"
        ),
        inline=False,
    )
    return embed


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def send_action_log(
    guild: discord.Guild,
    author: discord.abc.User,
    action: str,
    member: discord.Member | None = None,
    role: discord.Role | None = None,
    extra: str | None = None,
) -> None:
    guild_config = get_guild_config(guild.id)
    log_channel = get_channel_from_config(guild, guild_config.get("logs_channel_id"))
    if not isinstance(log_channel, discord.TextChannel):
        return

    embed = discord.Embed(title="Log", color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.add_field(name="Autor", value=author.mention, inline=False)
    embed.add_field(name="Acao", value=action, inline=False)
    if member is not None:
        embed.add_field(name="Membro", value=member.mention, inline=False)
    if role is not None:
        embed.add_field(name="Cargo", value=role.mention, inline=False)
    if extra:
        embed.add_field(name="Detalhes", value=extra, inline=False)
    await log_channel.send(embed=embed)


async def send_cargo_log(
    guild: discord.Guild,
    author: discord.abc.User,
    action: str,
    member: discord.Member,
    role: discord.Role,
) -> None:
    guild_config = get_guild_config(guild.id)
    log_channel = get_channel_from_config(guild, guild_config.get("cargo_logs_channel_id"))
    if not isinstance(log_channel, discord.TextChannel):
        return

    color = discord.Color.green() if action == "Cargo adicionado" else discord.Color.red()
    embed = discord.Embed(title="Log de Cargo", color=color, timestamp=datetime.utcnow())
    embed.add_field(name="Autor", value=author.mention, inline=False)
    embed.add_field(name="Acao", value=action, inline=False)
    embed.add_field(name="Membro", value=member.mention, inline=False)
    embed.add_field(name="Cargo", value=role.mention, inline=False)
    await log_channel.send(embed=embed)


async def ensure_ticket_category(guild: discord.Guild) -> discord.CategoryChannel:
    guild_config = get_guild_config(guild.id)
    category = get_channel_from_config(guild, guild_config.get("ticket_category_id"))
    if isinstance(category, discord.CategoryChannel):
        return category

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(TICKET_CATEGORY_NAME)

    update_guild_config(guild.id, "ticket_category_id", category.id)
    return category


def build_ticket_overwrites(
    guild: discord.Guild,
    user: discord.Member,
    reviewer_role: discord.Role | None,
) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        )
    if reviewer_role is not None:
        overwrites[reviewer_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )
    return overwrites


async def run_questionnaire(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    questions: list[str],
) -> None:
    user = interaction.user
    assert isinstance(user, discord.Member)

    sessions[user.id] = {
        "user": user.name,
        "user_id": user.id,
        "time": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "respostas": [],
    }

    try:
        for index, question in enumerate(questions, start=1):
            embed = discord.Embed(
                title=f"Pergunta {index} de {len(questions)}",
                description=question,
                color=discord.Color.blurple(),
            )
            embed.set_footer(text="Responda nesta sala em ate 5 minutos")
            await channel.send(content=user.mention, embed=embed)

            message = await bot.wait_for(
                "message",
                check=lambda msg: msg.author.id == user.id and msg.channel.id == channel.id,
                timeout=QUESTION_TIMEOUT,
            )
            sessions[user.id]["respostas"].append(
                {"pergunta": question, "resposta": message.content}
            )

        session = sessions[user.id]
        guild = interaction.guild
        if guild is None:
            await channel.send("Servidor nao encontrado.")
            return

        guild_config = get_guild_config(guild.id)
        transcript_channel = get_channel_from_config(
            guild,
            guild_config.get("transcripts_channel_id") or guild_config.get("logs_channel_id"),
        )
        embed = build_transcript_embed(session, channel.mention)
        view = TranscriptReviewView(session, user.id)

        if isinstance(transcript_channel, discord.TextChannel):
            review_message = await transcript_channel.send(embed=embed, view=view)
            view.message = review_message
            await channel.send("Transcript enviado para revisao.")
        else:
            await channel.send(embed=embed)
            await channel.send("Nenhum canal de transcript configurado. Configure com /configurar_canal ou /logs.")
    except TimeoutError:
        await channel.send(f"Tempo expirado para {user.mention}. Processo cancelado.")
    except Exception:
        logger.exception("Unexpected error in run_questionnaire for user %s", user.id)
        await channel.send("Ocorreu um erro inesperado. O canal sera deletado em breve.")
    finally:
        sessions.pop(user.id, None)
        await asyncio.sleep(CHANNEL_DELETION_DELAY_SECONDS)
        try:
            await channel.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            logger.warning("Failed to delete ticket channel %s", channel.id)


async def create_ticket_channel(interaction: discord.Interaction) -> discord.TextChannel | None:
    guild = interaction.guild
    user = interaction.user
    if guild is None or not isinstance(user, discord.Member):
        return None

    guild_config = get_guild_config(guild.id)
    reviewer_role = get_role_from_config(guild, guild_config.get("reviewer_role_id"))
    category = await ensure_ticket_category(guild)
    channel_name = f"ticket-{normalize_channel_slug(user.display_name)}"

    existing = discord.utils.get(category.text_channels, topic=f"ticket-owner:{user.id}")
    if existing is not None:
        return existing

    channel = await guild.create_text_channel(
        channel_name,
        category=category,
        overwrites=build_ticket_overwrites(guild, user, reviewer_role),
        topic=f"ticket-owner:{user.id}",
    )
    return channel


def user_is_staff(member: discord.Member, guild_config: dict) -> bool:
    staff_role_id = guild_config.get("staff_role_id")
    if not staff_role_id:
        return member.guild_permissions.manage_roles
    return any(role.id == staff_role_id for role in member.roles)


class TranscriptReviewView(discord.ui.View):
    def __init__(self, transcript_data: dict, user_id: int):
        super().__init__(timeout=None)
        self.transcript_data = transcript_data
        self.user_id = user_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        user = interaction.user
        if guild is None or not isinstance(user, discord.Member):
            await interaction.response.send_message("Interacao invalida.", ephemeral=True)
            return False

        reviewer_role_id = get_guild_config(guild.id).get("reviewer_role_id")
        reviewer_role = get_role_from_config(guild, reviewer_role_id)
        if reviewer_role is None or reviewer_role not in user.roles:
            await interaction.response.send_message(
                "Voce nao tem permissao para revisar transcripts.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Aceitar", style=discord.ButtonStyle.green, custom_id="transcript_accept")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
        file_name = f"transcript_{self.user_id}_{timestamp}.json"
        with open(file_name, "w", encoding="utf-8") as file:
            json.dump(self.transcript_data, file, ensure_ascii=False, indent=2)

        if self.message is not None:
            await self.message.edit(view=None)
        await interaction.response.send_message(
            f"Transcript aceito e salvo em {file_name}.",
            ephemeral=True,
        )
        if interaction.guild is not None:
            await send_action_log(
                interaction.guild,
                interaction.user,
                "Transcript aceito",
                extra=f"Arquivo salvo: {file_name}",
            )

    @discord.ui.button(label="Rejeitar", style=discord.ButtonStyle.red, custom_id="transcript_reject")
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.message is not None:
            await self.message.edit(view=None)
        await interaction.response.send_message("Transcript rejeitado.", ephemeral=True)
        if interaction.guild is not None:
            await send_action_log(interaction.guild, interaction.user, "Transcript rejeitado")


class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir ticket", style=discord.ButtonStyle.primary, custom_id="abrir_ticket")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        channel = await create_ticket_channel(interaction)
        if channel is None:
            await interaction.response.send_message("Nao foi possivel criar o ticket.", ephemeral=True)
            return

        await interaction.response.send_message(f"Ticket criado em {channel.mention}.", ephemeral=True)
        await run_questionnaire(interaction, channel, get_guild_questions(interaction.guild.id))


@bot.event
async def on_ready() -> None:
    bot.add_view(TicketButtonView())
    logger.info("Bot online como %s", bot.user)
    try:
        synced = await bot.tree.sync()
        logger.info("Slash commands sincronizados: %s", len(synced))
    except Exception:
        logger.exception("Falha ao sincronizar slash commands")


@bot.event
async def on_command_completion(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    await send_action_log(
        ctx.guild,
        ctx.author,
        "Comando de prefixo executado",
        extra=ctx.message.content,
    )


@bot.tree.command(name="configurar_canal", description="Define o canal onde os transcripts serao enviados")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_canal(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "transcripts_channel_id", canal.id)
    await interaction.response.send_message(
        f"Canal de transcripts definido para {canal.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="configurar_revisor", description="Define o cargo que pode revisar transcripts e tickets")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_revisor(interaction: discord.Interaction, cargo: discord.Role) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "reviewer_role_id", cargo.id)
    await interaction.response.send_message(
        f"Cargo revisor definido para {cargo.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="configurar_staff", description="Define o cargo staff para os comandos de cargo")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_staff(interaction: discord.Interaction, cargo: discord.Role) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "staff_role_id", cargo.id)
    await interaction.response.send_message(
        f"Cargo staff definido para {cargo.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="configurar_logs_sets", description="Canal onde os transcripts serao publicados")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_logs_sets(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "transcripts_channel_id", canal.id)
    await interaction.response.send_message(
        f"Canal de transcripts definido para {canal.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="logs", description="Define o canal de logs de acoes e comandos")
@app_commands.checks.has_permissions(administrator=True)
async def logs(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "logs_channel_id", canal.id)
    await interaction.response.send_message(
        f"Canal de logs definido para {canal.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="logs_cargo", description="Define o canal de logs exclusivo para adicao e remocao de cargos")
@app_commands.checks.has_permissions(administrator=True)
async def logs_cargo(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "cargo_logs_channel_id", canal.id)
    await interaction.response.send_message(
        f"Canal de logs de cargo definido para {canal.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="publicar_ticket", description="Publica o painel com botao para abrir ticket")
@app_commands.checks.has_permissions(administrator=True)
async def publicar_ticket(interaction: discord.Interaction) -> None:
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("Use este comando em um canal de texto do servidor.", ephemeral=True)
        return

    update_guild_config(interaction.guild.id, "ticket_panel_channel_id", interaction.channel.id)
    await interaction.channel.send("Clique no botao abaixo para abrir seu ticket.", view=TicketButtonView())
    await interaction.response.send_message("Painel de ticket publicado.", ephemeral=True)


@bot.tree.command(name="enviar_botao_ticket", description="Publica o painel de ticket no canal informado")
@app_commands.checks.has_permissions(administrator=True)
async def enviar_botao_ticket(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return
    update_guild_config(interaction.guild.id, "ticket_panel_channel_id", canal.id)
    await canal.send("Clique no botao abaixo para abrir seu ticket.", view=TicketButtonView())
    await interaction.response.send_message(f"Painel enviado em {canal.mention}.", ephemeral=True)


@bot.tree.command(name="configurar_perguntas", description="Define as perguntas do formulario para este servidor")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_perguntas(interaction: discord.Interaction, perguntas: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return

    separadores = ["\n", "|"]
    lista: list[str] = []
    for sep in separadores:
        if sep in perguntas:
            lista = [q.strip() for q in perguntas.split(sep) if q.strip()]
            break
    if not lista:
        lista = [perguntas.strip()]

    if len(lista) < 1:
        await interaction.response.send_message("Nenhuma pergunta valida encontrada.", ephemeral=True)
        return

    guild_config = get_guild_config(interaction.guild.id)
    guild_config["custom_questions"] = lista
    save_config(config)

    preview = "\n".join(f"{i}. {q}" for i, q in enumerate(lista, start=1))
    await interaction.response.send_message(
        f"Perguntas definidas ({len(lista)} no total):\n{preview}",
        ephemeral=True,
    )


@bot.tree.command(name="set", description="Cria um ticket e inicia as perguntas")
async def set_channel(interaction: discord.Interaction) -> None:
    channel = await create_ticket_channel(interaction)
    if channel is None:
        await interaction.response.send_message("Nao foi possivel criar o ticket.", ephemeral=True)
        return

    await interaction.response.send_message(f"Ticket criado em {channel.mention}.", ephemeral=True)
    await run_questionnaire(interaction, channel, get_guild_questions(interaction.guild.id))


@bot.tree.command(name="questoes", description="Faz as perguntas no canal atual")
async def questoes(interaction: discord.Interaction) -> None:
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("Use este comando em um canal de texto do servidor.", ephemeral=True)
        return

    if interaction.user.id in sessions:
        await interaction.response.send_message("Voce ja possui um formulario em andamento.", ephemeral=True)
        return

    await interaction.response.send_message("Perguntas iniciadas neste canal.", ephemeral=True)
    await run_questionnaire(interaction, interaction.channel, get_guild_questions(interaction.guild.id))


@commands.has_permissions(manage_roles=True)
@bot.command(name="addcargo")
async def addcargo(ctx: commands.Context, membro: discord.Member, cargo: discord.Role) -> None:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("Este comando so funciona em servidor.", delete_after=10)
        return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    guild_config = get_guild_config(ctx.guild.id)
    if not user_is_staff(ctx.author, guild_config):
        await ctx.send("Voce nao tem permissao para usar este comando.", delete_after=10)
        return

    if cargo >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("Voce nao pode gerenciar um cargo acima ou igual ao seu.", delete_after=10)
        return
    await membro.add_roles(cargo, reason=f"Adicionado por {ctx.author}")
    await ctx.send(f"Cargo {cargo.mention} adicionado a {membro.mention}.", delete_after=10)
    await send_cargo_log(ctx.guild, ctx.author, "Cargo adicionado", member=membro, role=cargo)


@commands.has_permissions(manage_roles=True)
@bot.command(name="remcargo")
async def remcargo(ctx: commands.Context, membro: discord.Member, cargo: discord.Role) -> None:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("Este comando so funciona em servidor.", delete_after=10)
        return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    guild_config = get_guild_config(ctx.guild.id)
    if not user_is_staff(ctx.author, guild_config):
        await ctx.send("Voce nao tem permissao para usar este comando.", delete_after=10)
        return

    if cargo >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("Voce nao pode gerenciar um cargo acima ou igual ao seu.", delete_after=10)
        return
    await membro.remove_roles(cargo, reason=f"Removido por {ctx.author}")
    await ctx.send(f"Cargo {cargo.mention} removido de {membro.mention}.", delete_after=10)
    await send_cargo_log(ctx.guild, ctx.author, "Cargo removido", member=membro, role=cargo)


@configurar_canal.error
@configurar_revisor.error
@configurar_staff.error
@configurar_logs_sets.error
@logs.error
@publicar_ticket.error
@enviar_botao_ticket.error
@configurar_perguntas.error
async def admin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.errors.MissingPermissions):
        if interaction.response.is_done():
            await interaction.followup.send("Voce precisa ser administrador para usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message("Voce precisa ser administrador para usar este comando.", ephemeral=True)
        return
    logger.exception("Erro em comando administrativo", exc_info=error)


@addcargo.error
@remcargo.error
async def prefix_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Voce precisa da permissao de gerenciar cargos.", delete_after=10)
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("Uso invalido. Exemplo: !addcargo @membro @cargo", delete_after=10)
        return
    logger.exception("Erro em comando de prefixo", exc_info=error)
    await ctx.send("Ocorreu um erro ao executar o comando.", delete_after=10)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Defina DISCORD_TOKEN no arquivo .env ou nas variaveis de ambiente.")
    bot.run(TOKEN)
