// Execute com: node frontend/tests/expense-values.test.cjs
const fs = require('node:fs');
const source = fs.readFileSync('frontend/js/central.js', 'utf8');
const functions = source.slice(source.indexOf('    function cents('), source.indexOf("    form.addEventListener('input'"));
new Function(functions + `
const assert = (condition, message) => { if (!condition) throw Error(message); };
const field = (value, decimals = 2) => {
    const input = { value: '', validity: {valid: true}, dataset: decimals ? {money: String(decimals)} : {} };
    setValue(input, value);
    return input;
};
const money = new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'});
const inputError = () => {}, markMissing = () => {}, updateRegistrationControls = () => {};
let totalsMismatch = false;
const notices = {};
const notice = (id, message) => { notices[id] = message; };
const values = [15.99,9.79,7.99,27.93,19.98,48.90,13.99,30,4.76,1.99,9.29,13.98,27.96,2.99,14.90];
const items = values.map(value => ({unidade:field('UN',0),quantidade:field(1,0),preco_unitario:field(value,4),preco_total:field(value),desconto:field(null)}));
const itemBody = {children:items.map(item=>({querySelector:selector=>item[selector.split('"')[1]]}))};
const controls = {'#exp-valor_total':field(250.44),'#exp-valor_pago':field(243.90),'#exp-desconto_total':field(6.54),'#items-empty':{}};
const $ = selector => controls[selector];
const allInputs = () => [...items.flatMap(Object.values), ...Object.values(controls).filter(input=>input.dataset)];
const form = {
    querySelectorAll: selector => allInputs().filter(input => input.dataset.calculated),
    querySelector: () => allInputs().find(input => input.dataset.calculated),
};
const sum = key => items.reduce((total,item)=>total+cents(amount(item[key])),0);
// As cinco linhas de desconto do comprovante: 0,83 + 1,40 + 1,00 + 2,94 + 0,37.
const printed = {1:0.83,3:1.40,4:1,5:2.94,8:0.37};
for (const [index, discount] of Object.entries(printed)) {
    setValue(items[index].desconto, discount);
    setValue(items[index].preco_total, null);
}
updateTotals();
assert(!totalsMismatch, 'Totais do comprovante devem conferir');
assert(sum('desconto') === 654, 'Descontos impressos somam R$ 6,54');
assert(sum('preco_total') === 24390, 'Itens líquidos devem somar R$ 243,90');
items.forEach((item,index)=>assert(amount(item.desconto)===(printed[index]||0), 'Preservar desconto do produto '+index));
const first = items.map(item=>item.desconto.value).join('|');
updateTotals(); updateTotals();
assert(items.map(item=>item.desconto.value).join('|') === first, 'Recalcular não pode alterar descontos impressos');
// Um desconto geral maior não pode criar descontos individuais.
setValue(controls['#exp-valor_pago'], 240); updateTotals();
assert(sum('desconto') === 654, 'Desconto geral não pode ser rateado');
assert(amount(controls['#exp-desconto_total']) === 6.54, 'Não substituir desconto total lido');
assert(totalsMismatch, 'Pagamento divergente exige revisão, não recalcular desconto lido');
// Uma leitura contraditória deve solicitar revisão, preservando o desconto lido.
setValue(items[1].preco_total, 9.79); delete items[1].preco_total.dataset.calculated;
updateTotals();
assert(totalsMismatch, 'Valores contraditórios exigem revisão');
assert(amount(items[1].desconto) === 0.83, 'Não apagar desconto lido para forçar fechamento');
// Sem descontos individuais, todos os totais originais devem permanecer.
items.forEach((item,index)=>{
    delete item.desconto.dataset.calculated; delete item.preco_total.dataset.calculated;
    setValue(item.desconto,null); setValue(item.preco_total,values[index]);
});
updateTotals();
assert(sum('desconto') === 0 && sum('preco_total') === 25044, 'Não inventar descontos ausentes');
assert(items.every(item=>item.desconto.value === ''), 'Desconto não identificado deve ficar vazio, não zero');
const currency = field(1234.56);
assert(currency.value.replace(/\\s/g,'') === 'R$1.234,56', 'Formato BRL');
assert(serializedValue(currency) === 1234.56, 'API recebe número sem máscara');
assert(serializedValue(field(0)) === 0, 'Zero não pode virar nulo');
assert(serializedValue(field(null)) === null, 'Vazio não pode virar zero');
assert(serializedValue(field(1.2345,4)) === 1.2345, 'Preço unitário preserva quatro casas');
for (const invalid of ['-1,00','abc','1,234','1.23,45','1,2,3']) {
    currency.value = invalid;
    assert(monetaryValue(currency) === null, 'Rejeitar valor inválido: '+invalid);
}
// Cupom com cinco descontos, dois produtos por peso e total bruto calculado.
const receipt = [
    [1,19.99,0,19.99], [2,29.59,0,59.18], [2,7.99,2,13.98], [2,7.99,2,13.98],
    [0.224,59.90,0,13.42], [0.380,89.90,0,34.16], [1,7.98,1.80,6.18],
    [1,8.99,1.50,7.49], [1,2.89,0,2.89], [2,3.89,2.20,5.58], [2,5.39,0,10.78],
];
items.splice(0, items.length, ...receipt.map(([quantity,price,discount,net],i) => ({
    unidade:field(i === 4 || i === 5 ? 'KG' : 'UN',0), quantidade:field(quantity,0),
    preco_unitario:field(price,4), desconto:field(discount), preco_total:field(net),
})));
itemBody.children = items.map(item=>({querySelector:selector=>item[selector.split('"')[1]]}));
Object.values(controls).forEach(input=>{ if (input.dataset) delete input.dataset.calculated; });
setValue(controls['#exp-valor_total'],197.13);
controls['#exp-valor_total'].dataset.calculated = 'true';
setValue(controls['#exp-desconto_total'],9.50);
setValue(controls['#exp-valor_pago'],187.63);
updateTotals(); updateTotals();
assert(!totalsMismatch, 'Cupom com pesos e descontos deve conferir');
assert(amount(controls['#exp-valor_total']) === 197.13, 'Bruto é a soma dos produtos, não o pagamento');
assert(amount(controls['#exp-desconto_total']) === 9.50, 'Preservar desconto total de R$ 9,50');
assert(sum('preco_total') === 18763, 'Líquido deve fechar em R$ 187,63');
assert(amount(items[4].quantidade) === 0.224 && amount(items[5].quantidade) === 0.380, 'Preservar pesos decimais');
// A leitura confundiu bruto e pagamento: não apagar o desconto impresso.
delete controls['#exp-valor_total'].dataset.calculated;
setValue(controls['#exp-valor_total'],187.63);
updateTotals();
assert(totalsMismatch, 'Bruto incorreto deve exigir revisão');
assert(amount(controls['#exp-desconto_total']) === 9.50, 'Não zerar o desconto ao confundir bruto com pago');
setValue(controls['#exp-desconto_total'],null);
updateTotals();
assert(amount(controls['#exp-desconto_total']) === null, 'Não calcular desconto zero de totais incoerentes');
`)();
console.log('Descontos impressos, ausência de rateio, recálculo e moeda: OK');
