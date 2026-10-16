// Table views for the analytics pages: every chart has an accessible table twin.

export interface TableColumn<T> {
  label: string;
  value: (row: T) => string | number;
  numeric?: boolean;
}

export function renderTable<T>(columns: TableColumn<T>[], rows: T[]): HTMLTableElement {
  const table = document.createElement("table");
  table.className = "min-w-full text-sm text-left";
  const headerRow = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column.label;
    cell.className = `px-2 py-1 font-semibold text-gray-700 border-b border-gray-200 ${column.numeric ? "text-right" : ""}`;
    headerRow.appendChild(cell);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tableRow = body.insertRow();
    for (const column of columns) {
      const cell = tableRow.insertCell();
      cell.textContent = String(column.value(row));
      cell.className = `px-2 py-1 border-b border-gray-100 text-gray-700 ${column.numeric ? "text-right tabular-nums" : ""}`;
    }
  }
  return table;
}
