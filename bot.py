import json
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"


class ConfigStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        if not self.file_path.exists():
            self._write({"guilds": {}})

    def _read(self) -> dict:
        with self.file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, indent=2)

    def get_guild(self, guild_id: int) -> dict:
        data = self._read()
        guild_key = str(guild_id)
        guild_data = data["guilds"].get(guild_key)
        if guild_data is None:
            guild_data = {
                "reviewer_role_id": None,
                "logs_channel_id": None,
                "ticket_category_id": None,
                "ticket_panel_channel_id": None,
            }
            data["guilds"][guild_key] = guild_data
            self._write(data)
        return guild_data

    def update_guild(self, guild_id: int, **kwargs) -> dict:
        data = self._read()
        guild_key = str(guild_id)
        current = data["guilds"].get(guild_key) or {
            "reviewer_role_id": None,
            "logs_channel_id": None,
            "ticket_category_id": None,
            "ticket_panel_channel_id": None,
        }
        current.update(kwargs)
        data["guilds"][guild_key] = current
        self._write(data)
        return current


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
config_store = ConfigStore(CONFIG_FILE)


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


async def send_log(guild: discord.Guild, title: str, description: str) -> None:
    cfg = config_store.get_guild(guild.id)
    channel_id = cfg.get("logs_channel_id")
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    await channel.send(embed=embed)


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.green, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Comando invalido fora de servidor.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        cfg = config_store.get_guild(guild.id)

        existing = discord.utils.get(guild.channels, name=f"ticket-{user.id}")
        if existing:
            await interaction.response.send_message(
                f"Voce ja possui um ticket aberto: {existing.mention}", ephemeral=True
            )
            return

        reviewer_role = guild.get_role(cfg.get("reviewer_role_id")) if cfg.get("reviewer_role_id") else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }

        if reviewer_role is not None:
            overwrites[reviewer_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        category = guild.get_channel(cfg.get("ticket_category_id")) if cfg.get("ticket_category_id") else None
        channel = await guild.create_text_channel(
            name=f"ticket-{user.id}",
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            reason=f"Ticket aberto por {user}",
        )

        embed = discord.Embed(
            title="Ticket criado",
            description="Explique seu pedido e aguarde um revisor responder.",
            color=discord.Color.blue(),
        )
        await channel.send(content=user.mention, embed=embed)
        await interaction.response.send_message(f"Seu ticket foi criado: {channel.mention}", ephemeral=True)
        await send_log(guild, "Ticket aberto", f"{user.mention} abriu {channel.mention}")


@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")
    except Exception as exc:
        print(f"Erro ao sincronizar slash commands: {exc}")
    print(f"Bot online como {bot.user}")


@bot.tree.command(name="publicartiket", description="Publica o painel de abertura de ticket")
@app_commands.describe(canal="Canal para publicar o painel", categoria="Categoria onde tickets serao criados")
async def publicartiket(
    interaction: discord.Interaction,
    canal: discord.TextChannel,
    categoria: discord.CategoryChannel | None = None,
):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return

    if not is_admin(interaction.user):
        await interaction.response.send_message("Apenas administradores podem usar este comando.", ephemeral=True)
        return

    config_store.update_guild(
        interaction.guild.id,
        ticket_category_id=categoria.id if categoria else None,
        ticket_panel_channel_id=canal.id,
    )

    embed = discord.Embed(
        title="Central de Tickets",
        description="Clique no botao abaixo para abrir seu ticket.",
        color=discord.Color.green(),
    )
    await canal.send(embed=embed, view=TicketPanel())
    await interaction.response.send_message("Painel de ticket publicado com sucesso.", ephemeral=True)
    await send_log(interaction.guild, "Painel de ticket", f"Painel publicado em {canal.mention}")


@bot.tree.command(name="configurarrevisor", description="Define o cargo que podera ver os tickets")
@app_commands.describe(cargo="Cargo de revisor")
async def configurarrevisor(interaction: discord.Interaction, cargo: discord.Role):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return

    if not is_admin(interaction.user):
        await interaction.response.send_message("Apenas administradores podem usar este comando.", ephemeral=True)
        return

    config_store.update_guild(interaction.guild.id, reviewer_role_id=cargo.id)
    await interaction.response.send_message(f"Cargo revisor configurado para {cargo.mention}", ephemeral=True)
    await send_log(interaction.guild, "Revisor configurado", f"Novo cargo revisor: {cargo.mention}")


@bot.tree.command(name="logs", description="Configura o canal de logs")
@app_commands.describe(canal="Canal onde os logs serao enviados")
async def logs(interaction: discord.Interaction, canal: discord.TextChannel):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        return

    if not is_admin(interaction.user):
        await interaction.response.send_message("Apenas administradores podem usar este comando.", ephemeral=True)
        return

    config_store.update_guild(interaction.guild.id, logs_channel_id=canal.id)
    await interaction.response.send_message(f"Canal de logs configurado: {canal.mention}", ephemeral=True)


@bot.command(name="addcargo")
@commands.has_permissions(manage_roles=True)
async def addcargo(ctx: commands.Context, membro: discord.Member, cargo: discord.Role):
    if ctx.guild is None:
        await ctx.reply("Use esse comando em um servidor.")
        return

    if cargo >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.reply("Voce nao pode gerenciar um cargo acima ou igual ao seu.")
        return

    await membro.add_roles(cargo, reason=f"Adicionado por {ctx.author}")
    await ctx.reply(f"Cargo {cargo.mention} adicionado para {membro.mention}.")
    await send_log(ctx.guild, "Cargo adicionado", f"{ctx.author.mention} adicionou {cargo.mention} em {membro.mention}")


@bot.command(name="remcargo")
@commands.has_permissions(manage_roles=True)
async def remcargo(ctx: commands.Context, membro: discord.Member, cargo: discord.Role):
    if ctx.guild is None:
        await ctx.reply("Use esse comando em um servidor.")
        return

    if cargo >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.reply("Voce nao pode gerenciar um cargo acima ou igual ao seu.")
        return

    await membro.remove_roles(cargo, reason=f"Removido por {ctx.author}")
    await ctx.reply(f"Cargo {cargo.mention} removido de {membro.mention}.")
    await send_log(ctx.guild, "Cargo removido", f"{ctx.author.mention} removeu {cargo.mention} de {membro.mention}")


@addcargo.error
@remcargo.error
async def role_cmd_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("Voce precisa da permissao de Gerenciar Cargos para usar esse comando.")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("Uso correto: !addcargo @membro @cargo / !remcargo @membro @cargo")
    else:
        await ctx.reply(f"Erro: {error}")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Defina DISCORD_TOKEN no .env ou nas variaveis de ambiente.")
    bot.run(TOKEN)
