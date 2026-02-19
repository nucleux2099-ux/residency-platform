import { fetchVaultTree } from "@/lib/api";
import { VaultTreeNode } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";

function TreeNode({ node, depth = 0 }: { node: VaultTreeNode; depth?: number }) {
  return (
    <div style={{ marginLeft: depth * 14 }}>
      <p style={{ margin: "4px 0", fontFamily: "monospace" }}>
        {node.is_dir ? "[DIR]" : "[FILE]"} {node.name}
      </p>
      {node.children.map((child) => (
        <TreeNode key={child.path} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

export default async function VaultPage({
  searchParams
}: {
  searchParams?: { folder?: string };
}) {
  const tree = await fetchVaultTree();
  const selectedFolder = searchParams?.folder;

  return (
    <section className="page">
      <PageHeader
        title="Vault Explorer"
        description="Live-indexed folder and file tree from backend. Sidebar tabs update via stream on filesystem changes."
      />
      {selectedFolder ? (
        <div className="kpi-strip">
          <div className="kpi-pill">
            <span className="kpi-pill__label">Selected Folder</span>
            <span className="kpi-pill__value">{selectedFolder}</span>
          </div>
        </div>
      ) : null}
      <div className="panel">
        <div className="panel__body" style={{ maxHeight: "72vh", overflow: "auto" }}>
        <TreeNode node={tree} />
        </div>
      </div>
    </section>
  );
}
