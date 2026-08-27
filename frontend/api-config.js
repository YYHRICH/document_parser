(function () {
  "use strict";

  var configured = "";
  try {
    configured = __DOCUMENT_PARSER_API_BASE_URL__;
  } catch (error) {
    configured = "";
  }
  if (typeof configured !== "string") configured = "";
  configured = configured.replace(/\/+$/, "");

  window.DocumentParserConfig = {
    apiBaseUrl: configured,
    url: function (path) {
      var value = String(path || "");
      if (!configured) return value;
      return configured + "/" + value.replace(/^\/+/, "");
    }
  };
}());
