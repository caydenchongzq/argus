/* Pure response guard, shared with the credential-free out-of-order fixture. */
globalThis.argusBrokerPreviewIsCurrent = function (
  requestId, latestRequestId, requestedAccountKey, selectedAccountKey, responseAccountKey, modalOpen,
) {
  return modalOpen
    && requestId === latestRequestId
    && requestedAccountKey === selectedAccountKey
    && requestedAccountKey === responseAccountKey;
};
// Backwards-compatible name for existing credential-free Tiger fixtures.
globalThis.argusTigerPreviewIsCurrent = globalThis.argusBrokerPreviewIsCurrent;
