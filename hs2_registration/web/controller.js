/* Private fixture registration controller; no public map/location export. */
(function (root) {
  class RegistrationController {
    constructor(request, render) { this.request = request; this.render = render; this.epoch = 0; this.state = null; this.busy = false; }
    async start(query) {
      return this.run("/hs2/registration/start", {query}, true);
    }
    async action(action, data = {}) {
      if (!this.state || this.busy) return;
      return this.run(`/hs2/registration/${this.state.workflow_id}/${action}`, data, false);
    }
    async run(url, body, reset) {
      const epoch = ++this.epoch;
      if (reset) this.state = null;
      this.busy = true;
      this.render(this.state, {busy:true});
      try {
        const result = await this.request(url, body);
        if (epoch !== this.epoch) return;
        if (result.error && !result.workflow_id) throw new Error(result.error);
        this.state = result;
        this.busy = false;
        this.render(result, {busy:false});
        return result;
      } catch (error) {
        if (epoch !== this.epoch) return;
        this.busy = false;
        this.state = null;
        const code = error && typeof error.code === "string" && /^[A-Z_]+$/.test(error.code)
          ? error.code : "REQUEST_FAILED";
        this.render(null, {busy:false, error:{code}});
      }
    }
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {RegistrationController};
  else root.RegistrationController = RegistrationController;
})(typeof window !== "undefined" ? window : globalThis);
