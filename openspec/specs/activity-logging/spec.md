# Activity Logging Specification

## Purpose

Structured user activity log with append-only file format and in-menu viewer. All significant menu actions are recorded for audit trail.

## Requirements

### Requirement: Log Format

SHALL write to `logs/user_activity.log`. Line format: `[YYYY-MM-DD HH:MM:SS] mensaje`. Append mode, UTF-8. Creates file + directory if missing. OSError MUST NOT break the menu.

#### Scenario: First write
- GIVEN logs/user_activity.log does not exist
- WHEN `_log_activity()` called
- THEN file created + first entry written

#### Scenario: Write error
- GIVEN disk full or permission denied
- WHEN `_log_activity()` called
- THEN menu continues without error

### Requirement: Logged Events

SHALL log these events via `_log_activity(mensaje: str)`:

| Event | Message format |
|-------|---------------|
| Menu start | "Menú iniciado" |
| Menu exit | "Menú finalizado" |
| Bot pause | "Usuario pausó el bot" |
| Bot resume | "Usuario reanudó el bot" |
| Force scan | "Usuario forzó escaneo" |
| Save strategy | "Estrategia '{name}' guardada" |
| Toggle strategy | "Estrategia '{name}' activada/desactivada" |
| Delete strategy | "Estrategia '{name}' eliminada" |
| Edit strategy | "Estrategia '{name}' editada" |
| Export trades | "Trades exportados a {filename}" |
| Alert change | "Usuario cambió umbral de {param} a {value}" |
| Simulation run | "Usuario ejecutó simulación de '{name}' cambiando '{param}' a {value}" |

### Requirement: Activity Viewer (Option 8)

SHALL show last 20 lines from `user_activity.log`. Function `_show_activity(state_loader, console)`. Same filter pattern as `_show_logs` (level filter optional, text search). Navigation: 0=Volver. GIVEN no file → "[dim]No hay registro de actividad[/]". GIVEN 50 entries → show last 20.

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Normal view | 50 entries in log | option 8 selected | last 20 lines shown |
| No activity | no log file exists | option 8 selected | "[dim]No hay registro de actividad[/]" |
| Search | — | text search with "pausó" | matching lines shown |
