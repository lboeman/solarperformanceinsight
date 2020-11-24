import Vue from "vue";
import Vuex from "vuex";
import App from "./App.vue";
import router from "./router";
import * as Sentry from "@sentry/browser";
import { Vue as VueIntegration } from "@sentry/integrations";
import { APIValidator } from "./types/validation/Validator";
import { spiStore } from "./store/store";
import { System } from "./types/System";
import  DemoSystems from "./types/demo/systems";

// Auth0 configuration
import { domain, clientId, audience } from "../auth_config.json";

import { Auth0Plugin } from "./auth/auth0";

Vue.use(Auth0Plugin, {
  domain,
  clientId,
  audience,
  onredirectCallback: appState => {
    router.push(
      appState && appState.targetUrl
      ? appState.targetUrl
      : window.location.pathname
    );
  }
});


Vue.config.productionTip = false;

if (process.env.NODE_ENV == "production") {
  Sentry.init({
    dsn:
      "https://624f863de69b4b1dabddc48e04329c5e@o481024.ingest.sentry.io/5528970",
    integrations: [new VueIntegration({ Vue })],
    // eslint-disable-next-line no-unused-vars
    beforeSend(event, hint) {
      // Check if it is an exception, and if so, show the report dialog
      if (event.exception) {
        Sentry.showReportDialog({ eventId: event.event_id });
      }
      return event;
    }
  });
}

Vue.use(Vuex);

Vue.config.productionTip = false;

const validator = new APIValidator();
validator.init();

const store = new Vuex.Store(spiStore);

Vue.prototype.$validator = validator;

if (process.env.NODE_ENV == "production"){
  console.log('were in production');
}

new Vue({
  router,
  render: h => h(App),
  store
}).$mount("#app");
