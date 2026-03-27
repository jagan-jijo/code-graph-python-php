interface SearchPanelProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchPanel({ value, onChange }: SearchPanelProps) {
  return (
    <section className="panel compact-panel">
      <div className="panel-header">
        <h2>Search</h2>
        <p>Filter nodes and connected edges by symbol, file, or module name.</p>
      </div>
      <label htmlFor="graph-search" className="sr-only">Search graph nodes</label>
      <input
        id="graph-search"
        className="search-input"
        type="search"
        placeholder="Search graph"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </section>
  );
}