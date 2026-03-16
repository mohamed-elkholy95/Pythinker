/**
 * Shell output sanitization utilities.
 *
 * The sandbox wraps command output in [CMD_BEGIN]/[CMD_END] markers for
 * reliable parsing. These markers are internal infrastructure plumbing
 * and must never reach the UI.
 */

const CMD_MARKER_REGEX = /\[CMD_(?:BEGIN|END)\]/g;

/**
 * Remove internal sandbox [CMD_BEGIN]/[CMD_END] markers from shell output.
 */
export const stripCmdMarkers = (text: string): string => text.replace(CMD_MARKER_REGEX, '');

/**
 * Clean PS1 prompt: strip markers, normalize whitespace, ensure ends with $.
 */
export const cleanPs1 = (ps1: string): string => {
  let cleaned = stripCmdMarkers(ps1).trim();
  if (cleaned && !cleaned.endsWith('$')) cleaned += ' $';
  return cleaned;
};

/**
 * Clean output: strip markers and remove duplicated header (ps1 + command echo).
 * The sandbox initializes output as [CMD_BEGIN]\n{ps1} {command}\n{actual output}.
 */
export const cleanShellOutput = (output: string, command?: string): string => {
  let cleaned = stripCmdMarkers(output);
  if (command) {
    const cmdIdx = cleaned.indexOf(`${command}\n`);
    if (cmdIdx >= 0) {
      cleaned = cleaned.substring(cmdIdx + command.length + 1);
    }
  }
  return cleaned.replace(/^\n+/, '');
};
