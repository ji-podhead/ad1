import * as React from "react";

export const Table = ({ children, ...props }: React.TableHTMLAttributes<HTMLTableElement>) => (
  <table {...props}>{children}</table>
);

export const TableHead = ({ children, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <thead {...props}>{children}</thead>
);

export const TableBody = ({ children, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <tbody {...props}>{children}</tbody>
);

export const TableRow = ({ children, ...props }: React.HTMLAttributes<HTMLTableRowElement>) => (
  <tr {...props}>{children}</tr>
);

export const TableCell = ({ children, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td {...props}>{children}</td>
);

export const TableHeader = ({ children, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th {...props}>{children}</th>
);
