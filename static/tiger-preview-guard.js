/* Pure response guard, shared with the credential-free out-of-order fixture. */
globalThis.argusTigerPreviewIsCurrent = function (
  requestId, latestRequestId, requestedAccountKey, selectedAccountKey, responseAccountKey, modalOpen,
) {
  return modalOpen
    && requestId === latestRequestId
    && requestedAccountKey === selectedAccountKey
    && requestedAccountKey === responseAccountKey;
};
