import discord


class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, *, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirmed: bool | None = None
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran this command can respond to this.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)


class CasesPaginatorView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        member: discord.abc.User,
        case_rows: list,
        guild: discord.Guild,
        per_page: int = 5,
    ):
        super().__init__(timeout=60.0)
        self.author_id = author_id
        self.member = member
        self.case_rows = case_rows
        self.guild = guild
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, (len(case_rows) - 1) // per_page)
        self.message: discord.Message | None = None
        self._update_button_states()

    def _update_button_states(self) -> None:
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        start = self.page * self.per_page
        page_rows = self.case_rows[start : start + self.per_page]

        embed = discord.Embed(
            title=f"Case History \u2014 {self.member}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=self.member.display_avatar.url)

        for row in page_rows:
            moderator = self.guild.get_member(row["moderator_id"])
            moderator_name = moderator.mention if moderator else f"ID {row['moderator_id']}"
            embed.add_field(
                name=f"Case #{row['id']} \u2014 {row['action_type'].upper()}",
                value=f"By {moderator_name}\nReason: {row['reason']}\n{row['created_at']}",
                inline=False,
            )

        embed.set_footer(text=f"Page {self.page + 1} of {self.max_page + 1} \u2014 {len(self.case_rows)} total cases")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran this command can page through this.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self.previous_button.disabled = True
        self.next_button.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
