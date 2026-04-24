export function getDefaultDateRange() {
  const dateTo = new Date();
  const dateFrom = new Date(dateTo);
  const day = dateTo.getDay();
  const daysSinceMonday = day === 0 ? 6 : day - 1;
  dateFrom.setDate(dateTo.getDate() - daysSinceMonday - 21);

  return {
    dateFrom: toIsoDate(dateFrom),
    dateTo: toIsoDate(dateTo),
  };
}

function toIsoDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
