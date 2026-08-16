import { app } from "../../scripts/app.js";

const NODE_CLASS = "TlantRandomLines";
const SYNC_TIMER = Symbol("tlantRandomLinesSyncTimer");
const SYNCING = Symbol("tlantRandomLinesSyncing");

function isConnected(output) {
    return Array.isArray(output?.links) && output.links.length > 0;
}

function syncOutputs(node) {
    if (node[SYNCING]) return;

    node[SYNCING] = true;
    try {
        for (let index = (node.outputs?.length ?? 0) - 1; index >= 0; index--) {
            if (!isConnected(node.outputs[index])) {
                node.removeOutput(index);
            }
        }

        const connected = node.outputs?.length ?? 0;
        node.addOutput(`line ${connected + 1}`, "STRING");

        for (let index = 0; index < node.outputs.length; index++) {
            const name = `line ${index + 1}`;
            node.outputs[index].name = name;
            node.outputs[index].label = name;
        }

        const size = node.computeSize();
        node.setSize([Math.max(node.size[0], size[0]), size[1]]);
        node.setDirtyCanvas(true, true);
    } finally {
        node[SYNCING] = false;
    }
}

function scheduleSync(node) {
    if (node[SYNC_TIMER]) clearTimeout(node[SYNC_TIMER]);
    node[SYNC_TIMER] = setTimeout(() => {
        node[SYNC_TIMER] = null;
        syncOutputs(node);
    }, 0);
}

app.registerExtension({
    name: "Tlant.RandomLines",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_CLASS) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            scheduleSync(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure?.apply(this, arguments);
            scheduleSync(this);
            return result;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type) {
            const result = onConnectionsChange?.apply(this, arguments);
            if (type === LiteGraph.OUTPUT) {
                if (app.configuringGraph) {
                    scheduleSync(this);
                } else {
                    syncOutputs(this);
                }
            }
            return result;
        };

        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            if (this[SYNC_TIMER]) clearTimeout(this[SYNC_TIMER]);
            return onRemoved?.apply(this, arguments);
        };
    },
});
