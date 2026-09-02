# Role picker (self-roles)

MEE6-style self-assign roles, built on Discord components instead of
reactions. Members pick from a dropdown; the bot swaps their role. This is
the first piece of the MEE6 replacement track and the thing the events
system tags when something is happening near you.

## What it does

- Posts a **panel**: an embed plus one select menu per group of up to 25
  options. Menus are persistent (fixed `custom_id`s, no stored state), so
  a restart never orphans one.
- **Exclusive panels** hold one role per member: picking Michigan removes
  Ohio. Clearing the menu removes the panel's role entirely.
- **Provisions roles** from the panel definition: `/roles post` creates
  whatever is missing (not hoisted, not mentionable by members, so only
  the bot can ping them) and posts the panel.
- Refuses, and says why, when the bot lacks Manage Roles or the guild
  would pass Discord's 250-role cap. Warns at 200.

Shipped panels in `penguin-overlord/assets/role_panels/`:

| key | roles | menus |
| --- | --- | --- |
| `country` | US and Canada first, 22 common countries, International | 1 |
| `us_states` | 50 states + DC | 3 (alphabetical ranges) |
| `ca_provinces` | 13 provinces and territories | 1 |

Roles are named plainly (`Michigan`, `Ontario`, `Canada`) so other
features resolve a region to a role by name.

## Setup

1. Give the bot **Manage Roles** and drag its role **above** where the
   picker roles will sit (new roles are created at the bottom, so above
   the member roles is enough).
2. `ROLE_PICKER_ENABLED=true` in `.env`, recreate the container.
3. In the roles channel: `/roles post country`, `/roles post us_states`,
   `/roles post ca_provinces`. Each creates its missing roles and posts.
4. `/roles list` shows every panel and how many of its roles exist.

`/roles` defaults to members with Manage Roles; adjust in Server Settings
> Integrations if moderators without it should post panels.

## Adding or changing a panel

Drop a JSON file in `assets/role_panels/`:

```json
{
  "key": "pronouns",
  "title": "Pronouns",
  "description": "Pick what fits. Change any time.",
  "exclusive": false,
  "groups": [
    {"placeholder": "Pronouns", "options": [
      {"label": "he/him", "role": "he/him"},
      {"label": "she/her", "role": "she/her"},
      {"label": "they/them", "role": "they/them"}
    ]}
  ]
}
```

Limits: 25 options per group, 5 groups per panel, role names 100 chars.
`exclusive: false` lets a member hold several (a menu still sets one at a
time; picking another adds it). Reposting a panel is safe: it only creates
roles that are missing and posts a fresh copy; delete the old message by
hand.

## Notes

- Menus answer ephemerally ("You are now **Michigan**. Swapped out
  Ohio."), so the roles channel stays clean.
- The bot never removes a role it did not define in the panel.
- If a role in a panel was deleted by hand, members get "not set up yet,
  ask a moderator to run /roles post" and the log records which role.
