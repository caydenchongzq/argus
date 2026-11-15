/* Pure numeric formatters shared by the UI and offline rendering fixtures. */
globalThis.argusFormatters = {
  escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  },
  moneyLevel(value, abbreviate = false) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    const number = Number(value);
    const absolute = Math.abs(number);
    if (abbreviate && absolute >= 1_000_000) {
      const amount = `$${(absolute / 1_000_000).toFixed(2)}M`;
      return number < 0 ? `−${amount}` : amount;
    }
    const digits = absolute > 0 && absolute < 0.01 ? 4 : 2;
    const amount = `$${absolute.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
    return number < 0 ? `−${amount}` : amount;
  },
  quantity(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    let text = String(value).trim();
    const scientific = /^([+-]?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(text);
    if (scientific) {
      const sign = scientific[1] === "-" ? "-" : "";
      const digits = scientific[2] + (scientific[3] || "");
      const point = scientific[2].length + Number(scientific[4]);
      text = point <= 0
        ? `0.${"0".repeat(-point)}${digits}`
        : point >= digits.length
          ? `${digits}${"0".repeat(point - digits.length)}`
          : `${digits.slice(0, point)}.${digits.slice(point)}`;
      text = sign + text;
    }
    const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
    if (!match) return "—";
    const sign = match[1] === "-" ? "−" : "";
    const whole = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    const fraction = (match[3] || "").replace(/0+$/, "");
    return `${sign}${whole}${fraction ? `.${fraction}` : ""}`;
  },
};
